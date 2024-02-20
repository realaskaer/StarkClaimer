import asyncio
import hmac
import time

from hashlib import sha256
from modules import CEX, Logger
from modules.interfaces import SoftwareExceptionWithoutRetry
from utils.tools import helper


class Binance(CEX, Logger):
    def __init__(self, client):
        self.client = client
        Logger.__init__(self)
        CEX.__init__(self, client, 'Binance')

        self.api_url = "https://api.binance.com"
        self.headers = {
            "Content-Type": "application/json",
            "X-MBX-APIKEY": self.api_key,
        }

    @staticmethod
    def parse_params(params: dict | None = None):
        if params:
            sorted_keys = sorted(params)
            params_str = "&".join(["%s=%s" % (x, params[x]) for x in sorted_keys])
        else:
            params_str = ''
        return params_str + "&timestamp=" + str(int(time.time() * 1000))

    def get_sign(self, payload: str = ""):
        try:
            secret_key_bytes = self.api_secret.encode('utf-8')
            signature = hmac.new(secret_key_bytes, payload.encode('utf-8'), sha256).hexdigest()

            return signature
        except Exception as error:
            raise SoftwareExceptionWithoutRetry(f'Bad signature for Binance request: {error}')

    async def deposit(self):
        pass

    async def get_currencies(self, ccy):
        path = '/sapi/v1/capital/config/getall'

        params = {
            'timestamp': str(int(time.time() * 1000))
        }

        parse_params = self.parse_params(params)

        url = f"{self.api_url}{path}?{parse_params}&signature={self.get_sign(parse_params)}"
        data = await self.make_request(url=url, headers=self.headers, module_name='Token info')
        return [item for item in data if item['coin'] == ccy]

    async def get_sub_list(self):
        path = "/sapi/v1/sub-account/list"

        parse_params = self.parse_params()
        url = f"{self.api_url}{path}?{parse_params}&signature={self.get_sign(parse_params)}"

        await asyncio.sleep(2)
        return await self.make_request(url=url, headers=self.headers, module_name='Get subAccounts list')

    async def get_sub_balance(self, sub_email):
        path = '/sapi/v3/sub-account/assets'

        params = {
            "email": sub_email
        }

        parse_params = self.parse_params(params)
        url = f"{self.api_url}{path}?{parse_params}&signature={self.get_sign(parse_params)}"

        await asyncio.sleep(2)
        return await self.make_request(url=url, headers=self.headers, module_name='Get subAccount balance')

    async def get_main_balance(self):
        path = '/sapi/v3/asset/getUserAsset'

        parse_params = self.parse_params()
        url = f"{self.api_url}{path}?{parse_params}&signature={self.get_sign(parse_params)}"

        await asyncio.sleep(2)
        return await self.make_request(method='POST', url=url, headers=self.headers, content_type=None,
                                       module_name='Get main account balance')

    async def transfer_from_subaccounts(self, ccy: str = 'ETH', amount: float = None, silent_mode:bool = False):
        if ccy == 'USDC.e':
            ccy = 'USDC'

        if not silent_mode:
            self.logger_msg(*self.client.acc_info, msg=f'Checking subAccounts balance')

        flag = True
        sub_list = (await self.get_sub_list())['subAccounts']

        for sub_data in sub_list:
            sub_email = sub_data['email']

            sub_balances = await self.get_sub_balance(sub_email)
            asset_balances = [balance for balance in sub_balances['balances'] if balance['asset'] == ccy]
            sub_balance = 0.0 if len(asset_balances) == 0 else float(asset_balances[0]['free'])

            if sub_balance != 0.0:
                flag = False
                amount = amount if amount else sub_balance
                self.logger_msg(*self.client.acc_info, msg=f'{sub_email} | subAccount balance : {sub_balance} {ccy}')

                params = {
                    "amount": amount,
                    "asset": ccy,
                    "fromAccountType": "SPOT",
                    "toAccountType": "SPOT",
                    "fromEmail": sub_email
                }

                path = "/sapi/v1/sub-account/universalTransfer"
                parse_params = self.parse_params(params)

                url = f"{self.api_url}{path}?{parse_params}&signature={self.get_sign(parse_params)}"
                await self.make_request(method="POST", url=url, headers=self.headers, module_name='SubAccount transfer')

                self.logger_msg(*self.client.acc_info,
                                msg=f"Transfer {amount} {ccy} to main account complete", type_msg='success')

                break
        if flag and not silent_mode:
            self.logger_msg(*self.client.acc_info, msg=f'subAccounts balance: 0 {ccy}', type_msg='warning')
        return True

    async def get_cex_balances(self, ccy: str = 'ETH'):
        if ccy == 'USDC.e':
            ccy = 'USDC'

        balances = {}

        main_balance = await self.get_main_balance()

        available_balance = [balance for balance in main_balance if balance['asset'] == ccy]

        if available_balance:
            balances['Main CEX Account'] = float(available_balance[0]['free'])

        sub_list = (await self.get_sub_list())['subAccounts']

        for sub_data in sub_list:
            sub_name = sub_data['email']
            sub_balances = await self.get_sub_balance(sub_name)
            balances[sub_name] = float(
                [balance for balance in sub_balances['balances'] if balance['asset'] == ccy][0]['free'])

            await asyncio.sleep(3)

        return balances

    async def wait_deposit_confirmation(self, amount: float, old_balances: dict, ccy: str = 'ETH',
                                        check_time: int = 45, timeout: int = 1200):

        if ccy == 'USDC.e':
            ccy = 'USDC'

        self.logger_msg(*self.client.acc_info, msg=f"Start checking CEX balances")

        await asyncio.sleep(10)
        total_time = 0
        while total_time < timeout:
            new_sub_balances = await self.get_cex_balances(ccy=ccy)
            for acc_name, acc_balance in new_sub_balances.items():

                if acc_balance > old_balances[acc_name]:
                    self.logger_msg(*self.client.acc_info, msg=f"Deposit {amount} {ccy} complete", type_msg='success')
                    return True
                else:
                    continue
            else:
                total_time += check_time
                self.logger_msg(*self.client.acc_info, msg=f"Deposit still in progress...", type_msg='warning')
                await asyncio.sleep(check_time)

        self.logger_msg(*self.client.acc_info, msg=f"Deposit does not complete in {timeout} seconds", type_msg='error')

    @helper
    async def transfer_from_subs(self):
        ccy = 'STRK'
        amount = None
        await self.transfer_from_subaccounts(ccy=ccy, amount=amount)
