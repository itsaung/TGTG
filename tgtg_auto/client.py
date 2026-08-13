"""TGTG client with card payment support.

The upstream `tgtg` package (ahivert/tgtg-python) handles auth, favourites and
order creation, but has no payment code at all. This subclass adds back the
Adyen card payment that the original tgtg_auto fork carried, on top of the
maintained client.
"""

import json
import random
import sys
from http import HTTPStatus
from urllib.parse import urljoin

import requests
from py_adyen_encrypt import encryptor
from tgtg import TgtgClient
from tgtg.exceptions import TgtgAPIError
from tgtg.google_play_scraper import get_last_apk_version

BASE_URL_ADYEN = "https://checkoutshopper-live.adyen.com/"
ADYEN_KEY_ENDPOINT = "checkoutshopper/v1/clientKeys/live_VPX45BIMLFAIVARYVKEDNC7OXIFBRQZ5"
ADYEN_ENCRYPTION_VERSION = "_0_1_1"

PAY_ORDER_ENDPOINT = "order/v{}/{}/pay"
PAYMENT_STATUS_ENDPOINT = "payment/v3/{}"

# The pay endpoint changed shape between versions: v7 takes a single
# "authorization" object, v8 takes an "authorizations" list. v8 matches the
# order/v8 endpoints the rest of the client uses, so it is tried first and we
# fall back to v7 if the API rejects the payload.
PAY_API_VERSIONS = (8, 7)

# The user agents shipped by the upstream package are old Android builds and
# currently get a DataDome captcha (403) on the auth endpoints. Recent builds
# get through.
USER_AGENTS = [
    "TGTG/{} Dalvik/2.1.0 (Linux; U; Android 14; Pixel 7 Pro Build/UQ1A.240205.004)",
    "TGTG/{} Dalvik/2.1.0 (Linux; U; Android 13; SM-S908B Build/TP1A.220624.014)",
    "TGTG/{} Dalvik/2.1.0 (Linux; U; Android 14; SM-A546B Build/UP1A.231005.007)",
]
DEFAULT_APK_VERSION = "26.8.0"


class TgtgPayClient(TgtgClient):
    def _get_user_agent(self):
        try:
            self.version = get_last_apk_version()
        except Exception:
            self.version = DEFAULT_APK_VERSION
            sys.stdout.write("Failed to get last version\n")

        sys.stdout.write(f"Using version {self.version}\n")

        return random.choice(USER_AGENTS).format(self.version)

    def _get_adyen_public_key(self):
        response = requests.get(
            urljoin(BASE_URL_ADYEN, ADYEN_KEY_ENDPOINT),
            headers={"User-Agent": self.user_agent},
            timeout=self.timeout,
        )
        if response.status_code != HTTPStatus.OK:
            raise TgtgAPIError(response.status_code, response.content)
        return response.json()["publicKey"]

    def _build_authorization(self, card_data):
        enc = encryptor(self._get_adyen_public_key())
        enc.adyen_version = ADYEN_ENCRYPTION_VERSION
        card = enc.encrypt_card(
            card=card_data["card"],
            cvv=card_data["cvv"],
            month=card_data["month"],
            year=card_data["year"],
        )

        inner_payload = {
            "type": "scheme",
            "encryptedCardNumber": card["card"],
            "encryptedExpiryMonth": card["month"],
            "encryptedExpiryYear": card["year"],
            "encryptedSecurityCode": card["cvv"],
            "threeDS2SdkVersion": "2.2.10",
        }

        return {
            "authorization_payload": {
                # the app sends the payload as an escaped JSON string
                "payload": json.dumps(inner_payload).replace("/", "\\/"),
                "payment_type": "CREDITCARD",
                "save_payment_method": False,
                "type": "adyenAuthorizationPayload",
            },
            "payment_provider": "ADYEN",
            "return_url": "adyencheckout://com.app.tgtg.itemview",
        }

    def pay_order(self, order_id, card_data, api_versions=PAY_API_VERSIONS):
        """Pay an order with card details.

        card_data: {"card": ..., "cvv": ..., "month": ..., "year": ...}
        """
        self.login()

        authorization = self._build_authorization(card_data)
        last_response = None

        for version in api_versions:
            if version >= 8:
                payload = {"authorizations": [authorization]}
            else:
                payload = {"authorization": authorization}

            response = self._post(
                self._get_url(PAY_ORDER_ENDPOINT.format(version, order_id)),
                data=json.dumps(payload),
            )
            if response.status_code == HTTPStatus.OK:
                return response.json()

            last_response = response
            # only a schema/route mismatch is worth retrying on another version;
            # a declined card or an expired order should surface as-is
            if response.status_code not in (
                HTTPStatus.BAD_REQUEST,
                HTTPStatus.NOT_FOUND,
            ):
                break
            sys.stdout.write(
                f"pay v{version} rejected ({response.status_code}), trying next version\n"
            )

        raise TgtgAPIError(last_response.status_code, last_response.content)

    def get_payment_status(self, payment_id):
        self.login()
        response = self._post(self._get_url(PAYMENT_STATUS_ENDPOINT.format(payment_id)))
        if response.status_code == HTTPStatus.OK:
            return response.json()
        raise TgtgAPIError(response.status_code, response.content)
