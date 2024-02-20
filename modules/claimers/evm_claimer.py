import asyncio
from time import time
from datetime import datetime, timezone

from eth_account.messages import encode_structured_data, encode_defunct

from modules import Logger, Client
from modules.interfaces import RequestClient, SoftwareException
from settings import TWO_CAPTCHA_API_KEY, CLAIM_RECIPIENT_ADDRESS
from utils.tools import helper


class ClaimerEVM(Logger, RequestClient):
    def __init__(self, client: Client):
        self.client = client
        Logger.__init__(self)

    async def get_sign_evm_structured_data(self):

        permit_data = {
            "domain": {
                "name": "PROVISIONS",
                "version": "1.0.0",
                "chainId": 1
            },
            "primaryType": "ClaimContractRequest",
            "types": {
                "EIP712Domain": [
                    {
                        "name": "name",
                        "type": "string"
                    },
                    {
                        "name": "version",
                        "type": "string"
                    },
                    {
                        "name": "chainId",
                        "type": "uint256"
                    }
                ],
                "ClaimContractRequest": [
                    {
                        "name": "claimContractId",
                        "type": "string"
                    },
                    {
                        "name": "claimContractRecipient",
                        "type": "string"
                    }
                ]
            },
            "message": {
                "claimContractId": "0x45a654",
                "claimContractRecipient": hex(CLAIM_RECIPIENT_ADDRESS)
            }
        }

        text_encoded = encode_structured_data(permit_data)
        sign_message = self.client.w3.eth.account.sign_message(text_encoded, private_key=self.client.private_key)

        return str(sign_message).split("signature=")[-1].replace("HexBytes('", '').replace("'))",'')

    def get_sign_evm_message_data(self):
        date = datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S")
        nonce = f"{time():.3f}"
        nonse_str = f"v3-{nonce}"

        text = (f"To protect your rhino.fi privacy we ask you to sign in with your wallet to see your data.\n"
                f"Signing in on {date} GMT. For your safety, only sign this message on rhino.fi!")

        text_hex = "0x" + text.encode('utf-8').hex()
        text_encoded = encode_defunct(hexstr=text_hex)
        signed_message = self.client.w3.eth.account.sign_message(text_encoded, private_key=self.client.private_key)

        return str(signed_message).split("signature=")[-1].replace("HexBytes('", '').replace("'))",'')

    async def create_task_for_captcha(self):
        url = 'https://api.anti-captcha.com/createTask'

        payload = {
            "clientKey": TWO_CAPTCHA_API_KEY,
            "task": {
                "type": "ReCaptchaV3TaskProxyless",
                "websiteURL": "https://provisions.starknet.io/",
                "websiteKey": "6Ldj1WopAAAAAGl194Fj6q-HWfYPNBPDXn-ndFRq",
                "pageAction": "home_page",
                "minScore": 0.8,
            }
        }

        response = await self.make_request(method="POST", url=url, json=payload)

        if not response['errorId']:
            return response['taskId']
        raise SoftwareException('Bad request to 2Captcha(Create Task)')

    async def get_captcha_key(self, task_id):
        url = 'https://api.anti-captcha.com/getTaskResult'

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

        self.logger_msg(*self.client.acc_info, msg=f'Stark Claiming $STRK')

        url = 'https://provisions.starknet.io/api/ethereum/claim'

        signature = await self.get_sign_evm_structured_data()

        task_id = await self.create_task_for_captcha()
        captcha_key = await self.get_captcha_key(task_id)

        headers = {
            'authority': "provisions.starknet.io",
            "method": "POST",
            "path": f"/api/ethereum/claim",
            "scheme": "https",
            "accept-Encoding": "gzip, deflate, br",
            "accept-Language": "ru,en;q=0.9,en-GB;q=0.8,en-US;q=0.7",
            "content-Length": "283",
            "content-Type": "application/json",
            "referer": "https://provisions.starknet.io/",
            "origin": "https://provisions.starknet.io",
            "sec-Ch-Ua": '"Not A(Brand";v="99", "Microsoft Edge";v="121", "Chromium";v="121"',
            "sec-Ch-Ua-Mobile": '?0',
            "sec-Ch-Ua-Platform": "Windows",
            "sec-Fetch-Dest": "empty",
            "sec-Fetch-Mode": 'cors',
            "sec-Fetch-Site": 'same-origin',
            "x-Kl-Saas-Ajax-Request": "Ajax_Request",
            "x-Recaptcha-Token": f"{captcha_key}"
        }

        payload = {
            "identity": self.client.address,
            "recipient": "{hex(CLAIM_RECIPIENT_ADDRESS)}",
            #"signature": signature
        }

        await self.make_request(method="POST", url=url, json=payload, headers=headers)

        self.logger_msg(*self.client.acc_info, msg=f'$STRK successfully claimed', type_msg='success')

    # @helper
    # async def claim_onchain(self):
    #     self.logger_msg(*self.client.acc_info, msg=f'On-chain claim $STRK')
    #     merkly_index = 0
    #     merkle_path = None
    #     for i in range(11):
    #         with open(f'./data/provision_data/starknet/starknet-{i}.json') as file:
    #             data = json.load(file)
    #             for item in data["eligibles"]:
    #                 if hex(int(item['identity'], 16)) == hex(self.client.address):
    #                     merkle_path = item['merkle_path']
    #                     amount_in_wei = to_wei(item['amount'], 'ether')
    #
    #     if merkle_path:
    #         transcation = await self.client.prepare_transaction()
    #             contract_address=ETHEREUM_CLAIM_CONTRACT,
    #             selector_name="claim",
    #             calldata=[
    #                 self.client.address,
    #                 amount_in_wei, 0,
    #                 merkly_index,
    #                 len(merkle_path),
    #                 *[int(i, 16) for i in merkle_path]
    #             ]
    #         )
    #
    #         return await self.client.send_transaction(claim_call)
    #     raise SoftwareException('This account is not eligible!')
