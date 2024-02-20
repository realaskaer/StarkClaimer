import asyncio
import json
from time import time

from datetime import datetime, timezone
from eth_account.messages import encode_defunct
from eth_utils import to_wei

from config import STARKNET_CLAIM_CONTRACT, ETHEREUM_CLAIM_CONTRACT
from modules import Logger, StarknetClient
from modules.interfaces import RequestClient, SoftwareException
from settings import TWO_CAPTCHA_API_KEY
from utils.tools import helper


class ClaimerStarknet(Logger, RequestClient):
    def __init__(self, client: StarknetClient):
        self.client = client
        Logger.__init__(self)

    async def get_sign_stark_structured_data(self):

        deadline = int(time()) + 10800

        typed_data = {
            "types": {
                "StarkNetDomain": [
                    {"name": "name", "type": "felt"},
                    {"name": "version", "type": "felt"},
                    {"name": "chainId", "type": "felt"},
                ],
                "Person": [
                    {"name": "name", "type": "felt"},
                    {"name": "wallet", "type": "felt"},
                ],
                "Mail": [
                    {"name": "from", "type": "Person"},
                    {"name": "to", "type": "Person"},
                    {"name": "contents", "type": "felt"},
                ],
            },
            "primaryType": "Mail",
            "domain": {"name": "StarkNet Mail", "version": "1", "chainId": 1},
            "message": {
                "from": {
                    "name": "Cow",
                    "wallet": "0xCD2a3d9F938E13CD947Ec05AbC7FE734Df8DD826",
                },
                "to": {
                    "name": "Bob",
                    "wallet": "0xbBbBBBBbbBBBbbbBbbBbbbbBBbBbbbbBbBbbBBbB",
                },
                "contents": "Hello, Bob!",
            },
        }

        signature = self.client.account.sign_message(typed_data=typed_data)
        if self.client.account.verify_message(typed_data=typed_data, signature=signature):
            return signature

        # data = TypedData.from_dict(typed_data)
        # message_hash = data.message_hash(self.client.account.address)

    def get_sign_stark_message_data(self):
        date = datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S")
        nonce = f"{time():.3f}"
        nonse_str = f"v3-{nonce}"

        text = (f"To protect your rhino.fi privacy we ask you to sign in with your wallet to see your data.\n"
                f"Signing in on {date} GMT. For your safety, only sign this message on rhino.fi!")

        text_hex = "0x" + text.encode('utf-8').hex()
        text_encoded = encode_defunct(hexstr=text_hex)
        signed_message = self.client.w3.eth.account.sign_message(text_encoded, private_key=self.client.private_key)

        return hex(signed_message.signature), signed_message.v, hex(signed_message.r), hex(signed_message.s)

    async def create_task_for_captcha(self):
        url = 'https://api.2captcha.com/createTask'

        payload = {
            "clientKey": TWO_CAPTCHA_API_KEY,
            "task": {
                "type": "RecaptchaV3TaskProxyless",
                "websiteURL": "https://provisions.starknet.io/",
                "websiteKey": "6Ldj1WopAAAAAGl194Fj6q-HWfYPNBPDXn-ndFRq",
                "pageAction": "submit",
            }
        }

        response = await self.make_request(method="POST", url=url, json=payload)

        if not response['errorId']:
            return response['taskId']
        raise SoftwareException('Bad request to 2Captcha(Create Task)')

    async def get_captcha_key(self, task_id):
        url = 'https://api.2captcha.com/getTaskResult'

        payload = {
            "clientKey": TWO_CAPTCHA_API_KEY,
            "taskId": task_id
        }

        total_time = 0
        timeout = 360
        while True:
            response = await self.make_request(method="POST", url=url, json=payload)

            if response['status'] == 'ready':
                return response['solution']['gRecaptchaResponse']

            total_time += 5
            await asyncio.sleep(5)

            if total_time > timeout:
                raise SoftwareException('Can`t get captcha solve in 360 second')

    @helper
    async def claim_strk_tokens(self):
        await self.client.initialize_account()

        self.logger_msg(*self.client.acc_info, msg=f'Stark Claiming $STRK')

        url = 'https://provisions.starknet.io/api/ethereum/getClaim'

        signature = await self.get_sign_stark_structured_data()

        signature = self.get_sign_stark_message_data()

        task_id = await self.create_task_for_captcha()
        captcha_key = await self.get_captcha_key(task_id)

        headers = {
            ':authority:': "provisions.starknet.io",
            ":method:": "GET",
            ":path:": f"/api/ethereum/get_eligibility?identity={self.client.address}",
            ":scheme:": "https",
            "Accept": "application/json, text/plain, */*",
            "Accept-Encoding": "gzip, deflate, br",
            "Accept-Language": "ru,en;q=0.9,en-GB;q=0.8,en-US;q=0.7",
            "Referer": "https://provisions.starknet.io/",
            "Sec-Ch-Ua": '"Not A(Brand";v="99", "Microsoft Edge";v="121", "Chromium";v="121"',
            "Sec-Ch-Ua-Mobile": '?0',
            "Sec-Ch-Ua-Platform": "Windows",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": 'cors',
            "Sec-Fetch-Site": 'same-origin',
            "X-Kl-Saas-Ajax-Request": "Ajax_Request",
            "X-Recaptcha-Token": f"{captcha_key}"
        }

        payload = {
            "address": f"{self.client.address}"
        }

        #response = await self.make_request(method="POST", url=url, params=params, json=params, headers=headers)

        self.logger_msg(*self.client.acc_info, msg=f'$STRK successfully claimed', type_msg='success')

    @helper
    async def claim_onchain(self):
        await self.client.initialize_account()

        self.logger_msg(*self.client.acc_info, msg=f'On-chain claim $STRK')
        merkly_index = 0
        amount = 0
        merkle_path = None
        for i in range(11):
            with open(f'./data/provision_data/starknet/starknet-{i}.json') as file:
                data = json.load(file)
                for item in data["eligibles"]:
                    if hex(int(item['identity'], 16)) == hex(self.client.address):
                        merkle_path = item['merkle_path']
                        amount = item['amount']
                        amount_in_wei = to_wei(item['amount'], 'ether')

        if merkle_path:
            self.logger_msg(
                *self.client.acc_info, msg=f'This wallet is eligible to claim {amount} $STRK', type_msg='success')

            claim_call = self.client.prepare_call(
                contract_address=ETHEREUM_CLAIM_CONTRACT,
                selector_name="claim",
                calldata=[
                    self.client.address,
                    amount_in_wei, 0,
                    merkly_index,
                    len(merkle_path),
                    *[int(i, 16) for i in merkle_path]
                ]
            )

            return await self.client.send_transaction(claim_call)
        raise SoftwareException('This account is not eligible!')
