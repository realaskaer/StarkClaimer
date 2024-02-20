import asyncio
import json
import random

from starknet_py.contract import Contract
from starknet_py.net.account.account import Account
from starknet_py.hash.address import compute_address
from starknet_py.net.client_errors import ClientError
from starknet_py.cairo.felt import decode_shortstring
from starknet_py.net.models.chains import StarknetChainId
from starknet_py.net.full_node_client import FullNodeClient
from starknet_py.hash.selector import get_selector_from_name
from starknet_py.net.signer.stark_curve_signer import KeyPair
from starknet_py.net.client_models import Call

from aiohttp import ClientSession, TCPConnector
from aiohttp_socks import ProxyConnector
from modules import Logger
from modules.interfaces import get_user_agent, SoftwareException
from utils.networks import Network
from config import (
    TOKENS_PER_CHAIN,
    ARGENT_IMPLEMENTATION_CLASS_HASH_NEW,
    BRAAVOS_PROXY_CLASS_HASH, BRAAVOS_IMPLEMENTATION_CLASS_HASH, ARGENT_PROXY_CLASS_HASH,
    ARGENT_IMPLEMENTATION_CLASS_HASH
)


from settings import USE_PROXY


class StarknetClient(Logger):
    def __init__(self, account_name: str, private_key: str, network: Network, proxy: None | str = None):
        Logger.__init__(self)
        self.network = network
        self.token = network.token
        self.explorer = network.explorer
        self.chain_id = StarknetChainId.MAINNET
        self.proxy = f"http://{proxy}" if proxy else ""
        self.proxy_init = proxy

        key_pair = KeyPair.from_private_key(private_key)
        self.key_pair = key_pair
        self.session = self.get_proxy_for_account(self.proxy)
        self.w3 = FullNodeClient(node_url=random.choice(network.rpc), session=self.session)

        self.account_name = account_name
        self.private_key = private_key
        self.acc_info = None
        self.account = None
        self.address = None
        self.WALLET_TYPE = None

    async def initialize_account(self, check_balance:bool = False):
        self.account, self.address, self.WALLET_TYPE = await self.get_wallet_auto(
            self.w3, self.key_pair,
            self.account_name, check_balance
        )

        self.address = int(self.address)
        self.acc_info = self.account_name, self.address
        self.account.ESTIMATED_FEE_MULTIPLIER = 1.5

    async def get_wallet_auto(self, w3, key_pair, account_name, check_balance:bool = False):
        last_data = await self.check_stark_data_file(account_name)
        if last_data:
            address, wallet_type = last_data['address'], last_data['wallet_type']

            account = Account(client=w3, address=address, key_pair=key_pair, chain=StarknetChainId.MAINNET)
            return account, address, wallet_type

        possible_addresses = [(self.get_argent_address(key_pair, 1), 0),
                              (self.get_braavos_address(key_pair), 1),
                              (self.get_argent_address(key_pair, 0), 0)]

        for address, wallet_type in possible_addresses:
            account = Account(client=w3, address=address, key_pair=key_pair, chain=StarknetChainId.MAINNET)
            try:
                if check_balance:
                    result = await account.get_balance(address)
                else:
                    result = await self.w3.get_class_hash_at(address)

                if result:
                    await self.save_stark_data_file(account_name, address, wallet_type)
                    return account, address, wallet_type
            except ClientError:
                pass

        raise RuntimeError('This wallet is not deployed!')

    @staticmethod
    def get_proxy_for_account(proxy):
        if USE_PROXY and proxy != "":
            return ClientSession(connector=ProxyConnector.from_url(f"{proxy}", verify_ssl=True))
        return ClientSession(connector=TCPConnector(verify_ssl=False))

    @staticmethod
    async def check_stark_data_file(account_name):
        bad_progress_file_path = './data/services/stark_data.json'
        try:
            with open(bad_progress_file_path, 'r') as file:
                data = json.load(file)
        except (FileNotFoundError, json.JSONDecodeError):
            data = {}

        if account_name in data:
            return data[account_name]

    @staticmethod
    async def save_stark_data_file(account_name, address, wallet_type):
        bad_progress_file_path = './data/services/stark_data.json'
        try:
            with open(bad_progress_file_path, 'r') as file:
                data = json.load(file)
        except (FileNotFoundError, json.JSONDecodeError):
            data = {}

        data[account_name] = {
            'address': address,
            'wallet_type': wallet_type,
        }

        with open(bad_progress_file_path, 'w') as file:
            json.dump(data, file, indent=4)

    @staticmethod
    def get_braavos_address(key_pair) -> int:
        selector = get_selector_from_name("initializer")
        call_data = [key_pair.public_key]

        return compute_address(
            class_hash=BRAAVOS_PROXY_CLASS_HASH,
            constructor_calldata=[BRAAVOS_IMPLEMENTATION_CLASS_HASH, selector, len(call_data), *call_data],
            salt=key_pair.public_key
        )

    @staticmethod
    def get_argent_address(key_pair, cairo_version) -> int:
        selector = get_selector_from_name("initialize")
        call_data = [key_pair.public_key, 0]

        if cairo_version:
            proxy_class_hash = ARGENT_IMPLEMENTATION_CLASS_HASH_NEW
            constructor_calldata = call_data
        else:
            proxy_class_hash = ARGENT_PROXY_CLASS_HASH
            constructor_calldata = [ARGENT_IMPLEMENTATION_CLASS_HASH, selector, len(call_data), *call_data]

        return compute_address(
            class_hash=proxy_class_hash,
            constructor_calldata=constructor_calldata,
            salt=key_pair.public_key
        )

    @staticmethod
    def round_amount(min_amount: float, max_amount:float) -> float:
        decimals = max(len(str(min_amount)) - 1, len(str(max_amount)) - 1)
        return round(random.uniform(min_amount, max_amount), decimals + 1)

    @staticmethod
    def get_normalize_error(error:Exception) -> Exception | str:
        try:
            if isinstance(error.args[0], dict):
                error = error.args[0].get('message', error)
            return error
        except:
            return error

    async def initialize_evm_client(self, private_key, chain_id):
        from modules import Client
        from functions import get_network_by_chain_id
        evm_client = Client(self.account_name, private_key,
                            get_network_by_chain_id(chain_id), self.proxy_init)
        return evm_client

    async def get_decimals(self, token_name:str):
        contract = TOKENS_PER_CHAIN[self.network.name][token_name]
        return (await self.account.client.call_contract(self.prepare_call(contract, 'decimals')))[0]

    async def get_normalize_amount(self, token_name, amount_in_wei):
        decimals = await self.get_decimals(token_name)
        return float(amount_in_wei / 10 ** decimals)

    async def get_smart_amount(self, settings:tuple, token_name:str = 'ETH'):
        if isinstance(settings[0], str):
            _, amount, _ = await self.get_token_balance(token_name)
            percent = round(random.uniform(float(settings[0]), float(settings[1])), 6) / 100
            amount = round(amount * percent, 6)
        else:
            amount = self.round_amount(*settings)
        return amount

    async def get_contract(self, contract_address: int, proxy_config: bool = False):
        return await Contract.from_address(address=contract_address, provider=self.account, proxy_config=proxy_config)

    @staticmethod
    def prepare_call(contract_address:int, selector_name:str, calldata:list = None):
        if calldata is None:
            calldata = []
        return Call(
            to_addr=contract_address,
            selector=get_selector_from_name(selector_name),
            calldata=[int(data) for data in calldata],
        )

    async def get_token_balance(self, token_name: str = 'ETH', check_symbol: bool = True) -> [float, int, str]:
        contract = TOKENS_PER_CHAIN[self.network.name][token_name]
        amount_in_wei = (await self.account.client.call_contract(self.prepare_call(contract, 'balanceOf',
                                                                                   [self.address])))[0]

        decimals = (await self.account.client.call_contract(self.prepare_call(contract, 'decimals')))[0]

        if check_symbol:
            symbol = decode_shortstring((await self.account.client.call_contract(
                self.prepare_call(contract, 'symbol')))[0])

            return amount_in_wei, amount_in_wei / 10 ** decimals, symbol
        return amount_in_wei, amount_in_wei / 10 ** decimals, ''

    def get_approve_call(self, token_address: int, spender_address: int,
                         amount_in_wei: int = None) -> Call:
        return self.prepare_call(token_address, 'approve', [
            spender_address,
            2 ** 128 - 1,
            2 ** 128 - 1
        ])

    async def send_transaction(self, *calls:list, check_hash:bool = False, hash_for_check:int = None):
        try:
            tx_hash = hash_for_check
            if not check_hash:
                tx_hash = (await self.account.execute_v1(
                    calls=calls,
                    auto_estimate=True
                )).transaction_hash

            await self.account.client.wait_for_tx(tx_hash, check_interval=20, retries=1000)

            self.logger_msg(
                *self.acc_info, msg=f'Transaction was successful: {self.explorer}tx/{hex(tx_hash)}', type_msg='success')
            return True

        except Exception as error:
            raise SoftwareException(f'Send transaction | {self.get_normalize_error(error)}')

    async def make_request(self, method:str = 'GET', url:str = None, headers:dict = None, params: dict = None,
                           data:str = None, json:dict = None, module_name:str = None):

        headers = (headers or {}) | {'User-Agent': get_user_agent()}
        async with self.session.request(method=method, url=url, headers=headers, data=data,
                                        params=params, json=json) as response:

            data = await response.json()
            if response.status == 200:
                return data
            raise SoftwareException(f"Bad request to {module_name} API: {response.status}")

    async def get_gas_price(self):
        url = 'https://alpha-mainnet.starknet.io/feeder_gateway/get_block?blockNumber=latest'

        headers = {
            'Content-Type': 'application/json; charset=utf-8'
        }

        data = (await self.make_request(url=url, headers=headers, module_name='Gas Price'))['strk_l1_gas_price']

        return int(data, 16) / 10 ** 7

    async def get_token_price(self, token_name: str, vs_currency: str = 'usd') -> float:
        await asyncio.sleep(10)
        url = 'https://api.coingecko.com/api/v3/simple/price'

        params = {'ids': f'{token_name}', 'vs_currencies': f'{vs_currency}'}

        async with self.session.get(url, params=params) as response:
            if response.status == 200:
                data = await response.json()
                return float(data[token_name][vs_currency])
            raise SoftwareException(f'Bad request to CoinGecko API: {response.status}')
