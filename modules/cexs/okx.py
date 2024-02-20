import hmac
import base64
import asyncio

from hashlib import sha256
from modules import CEX, Logger
from datetime import datetime, timezone

from modules.interfaces import SoftwareExceptionWithoutRetry
from utils.tools import helper


class OKX(CEX, Logger):
    def __init__(self, client):
        self.client = client
        Logger.__init__(self)
        CEX.__init__(self, client, "OKX")

    async def get_headers(self, request_path: str, method: str = "GET", body: str = ""):
        try:
            timestamp = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z'
            prehash_string = timestamp + method.upper() + request_path[19:] + body
            secret_key_bytes = self.api_secret.encode('utf-8')
            signature = hmac.new(secret_key_bytes, prehash_string.encode('utf-8'), sha256).digest()
            encoded_signature = base64.b64encode(signature).decode('utf-8')

            return {
                "Content-Type": "application/json",
                "OK-ACCESS-KEY": self.api_key,
                "OK-ACCESS-SIGN": encoded_signature,
                "OK-ACCESS-TIMESTAMP": timestamp,
                "OK-ACCESS-PASSPHRASE": self.passphras,
                "x-simulated-trading": "0"
            }
        except Exception as error:
            raise SoftwareExceptionWithoutRetry(f'Bad headers for OKX request: {error}')

    async def get_currencies(self, ccy: str = 'ETH'):
        url = 'https://www.okx.cab/api/v5/asset/currencies'

        params = {'ccy': ccy}

        headers = await self.get_headers(f'{url}?ccy={ccy}')

        return await self.make_request(url=url, headers=headers, params=params, module_name='Token info')

    @helper
    async def transfer_from_subaccounts(self, ccy:str = 'ETH', amount:float = None, silent_mode:bool = False):

        if ccy == 'USDC.e':
            ccy = 'USDC'

        if not silent_mode:
            self.logger_msg(*self.client.acc_info, msg=f'Checking subAccounts balance')

        url_sub_list = "https://www.okx.cab/api/v5/users/subaccount/list"

        flag = True
        headers = await self.get_headers(request_path=url_sub_list)
        sub_list = await self.make_request(url=url_sub_list, headers=headers, module_name='Get subAccounts list')
        await asyncio.sleep(1)

        for sub_data in sub_list:
            sub_name = sub_data['subAcct']

            url_sub_balance = f"https://www.okx.cab/api/v5/asset/subaccount/balances?subAcct={sub_name}&ccy={ccy}"
            headers = await self.get_headers(request_path=url_sub_balance)

            sub_balance = (await self.make_request(url=url_sub_balance, headers=headers,
                                                   module_name='Get subAccount balance'))

            if sub_balance:
                sub_balance = float(sub_balance[0]['availBal'])

            await asyncio.sleep(1)

            if sub_balance != 0.0:
                flag = False
                amount = amount if amount else sub_balance
                self.logger_msg(*self.client.acc_info, msg=f'{sub_name} | subAccount balance : {sub_balance} {ccy}')

                body = {
                    "ccy": ccy,
                    "type": "2",
                    "amt": f"{amount}",
                    "from": "6",
                    "to": "6",
                    "subAcct": sub_name
                }

                url_transfer = "https://www.okx.cab/api/v5/asset/transfer"
                headers = await self.get_headers(method="POST", request_path=url_transfer, body=str(body))
                await self.make_request(method="POST", url=url_transfer, data=str(body), headers=headers,
                                        module_name='SubAccount transfer')

                self.logger_msg(*self.client.acc_info,
                                msg=f"Transfer {amount} {ccy} to main account complete", type_msg='success')
        if flag and not silent_mode:
            self.logger_msg(*self.client.acc_info, msg=f'subAccounts balance: 0 {ccy}', type_msg='warning')
        return True

    @helper
    async def transfer_from_spot_to_funding(self, ccy:str = 'ETH'):

        await asyncio.sleep(5)

        if ccy == 'USDC.e':
            ccy = 'USDC'

        url_balance = f"https://www.okx.cab/api/v5/account/balance?ccy={ccy}"
        headers = await self.get_headers(request_path=url_balance)
        balance = (await self.make_request(url=url_balance, headers=headers,
                                           module_name='Trading account'))[0]["details"]

        for ccy_item in balance:
            if ccy_item['ccy'] == ccy and ccy_item['availBal'] != '0':

                self.logger_msg(
                    *self.client.acc_info, msg=f"Main trading account balance: {ccy_item['availBal']} {ccy}")

                body = {
                    "ccy": ccy,
                    "amt": ccy_item['availBal'],
                    "from": "18",
                    "to": "6"
                }

                url_transfer = "https://www.okx.cab/api/v5/asset/transfer"
                headers = await self.get_headers(request_path=url_transfer, body=str(body), method="POST")
                await self.make_request(url=url_transfer, data=str(body), method="POST", headers=headers,
                                        module_name='Trading account')
                self.logger_msg(*self.client.acc_info,
                                msg=f"Transfer {float(ccy_item['availBal']):.6f} {ccy} to funding account complete",
                                type_msg='success')
                break
            else:
                self.logger_msg(*self.client.acc_info, msg=f"Main trading account balance: 0 {ccy}", type_msg='warning')
                break

        return True

    async def get_cex_balances(self, ccy:str = 'ETH'):
        balances = {}
        url_sub_list = "https://www.okx.cab/api/v5/users/subaccount/list"

        await asyncio.sleep(10)

        if ccy == 'USDC.e':
            ccy = 'USDC'

        headers = await self.get_headers(request_path=url_sub_list)
        sub_list = await self.make_request(url=url_sub_list, headers=headers, module_name='Get subAccounts list')

        url_balance = f"https://www.okx.cab/api/v5/asset/balances?ccy={ccy}"

        headers = await self.get_headers(request_path=url_balance)

        balance = (await self.make_request(url=url_balance, headers=headers, module_name='Get Account balance'))

        if balance:
            balances['Main CEX Account'] = float(balance[0]['availBal'])

        for sub_data in sub_list:
            sub_name = sub_data['subAcct']

            url_sub_balance = f"https://www.okx.cab/api/v5/asset/subaccount/balances?subAcct={sub_name}&ccy={ccy}"
            headers = await self.get_headers(request_path=url_sub_balance)

            sub_balance = (await self.make_request(url=url_sub_balance, headers=headers,
                                                   module_name='Get subAccount balance'))
            await asyncio.sleep(3)

            if sub_balance:
                balances[sub_name] = float(sub_balance[0]['availBal'])

        return balances

    async def wait_deposit_confirmation(self, amount:float, old_sub_balances:dict, ccy:str = 'ETH',
                                        check_time:int = 45, timeout:int = 1200):

        if ccy == 'USDC.e':
            ccy = 'USDC'

        self.logger_msg(*self.client.acc_info, msg=f"Start checking CEX balances")

        await asyncio.sleep(10)
        total_time = 0
        while total_time < timeout:
            new_sub_balances = await self.get_cex_balances(ccy=ccy)
            for sub_name, sub_balance in new_sub_balances.items():
                if sub_balance > old_sub_balances[sub_name]:
                    self.logger_msg(*self.client.acc_info, msg=f"Deposit {amount} {ccy} complete", type_msg='success')
                    return True
                else:
                    continue
            else:
                total_time += check_time
                self.logger_msg(*self.client.acc_info, msg=f"Deposit still in progress...", type_msg='warning')
                await asyncio.sleep(check_time)

        raise SoftwareExceptionWithoutRetry(f"Deposit does not complete in {timeout} seconds")

    async def transfer_from_subs(self):
        ccy = 'STRK'
        amount = None

        await self.transfer_from_subaccounts(ccy=ccy, amount=amount)
        await self.transfer_from_spot_to_funding(ccy=ccy)
