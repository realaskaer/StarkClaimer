import asyncio
import random

from asyncio import sleep
from aiohttp import ClientSession, TCPConnector
from aiohttp_socks import ProxyConnector
from eth_typing import HexStr
from web3.contract import AsyncContract
from web3.exceptions import TransactionNotFound, TimeExhausted
from modules.interfaces import BlockchainException, SoftwareException
from modules import Logger
from utils.networks import Network
from config import ERC20_ABI, TOKENS_PER_CHAIN
from web3 import AsyncHTTPProvider, AsyncWeb3


class Client(Logger):
    def __init__(self, account_name: str | int, private_key: str, network: Network, proxy: None | str = None):
        Logger.__init__(self)
        self.network = network
        self.eip1559_support = network.eip1559_support
        self.token = network.token
        self.explorer = network.explorer
        self.chain_id = network.chain_id

        self.proxy_init = proxy
        self.session = ClientSession(connector=ProxyConnector.from_url(f"http://{proxy}", verify_ssl=False)
                                     if proxy else TCPConnector(verify_ssl=False))
        self.request_kwargs = {"proxy": f"http://{proxy}"} if proxy else {}
        self.rpc = random.choice(network.rpc)
        self.w3 = AsyncWeb3(AsyncHTTPProvider(self.rpc, request_kwargs=self.request_kwargs))
        self.account_name = str(account_name)
        self.private_key = private_key
        self.address = AsyncWeb3.to_checksum_address(self.w3.eth.account.from_key(private_key).address)
        self.acc_info = account_name, self.address

    @staticmethod
    def round_amount(min_amount: float, max_amount: float) -> float:
        decimals = max(len(str(min_amount)) - 1, len(str(max_amount)) - 1) + 1
        max_decimals = 6
        return round(random.uniform(min_amount, max_amount), decimals if decimals <= max_decimals else 6)

    @staticmethod
    def get_normalize_error(error: Exception) -> Exception | str:
        try:
            if isinstance(error.args[0], dict):
                error = error.args[0].get('message', error)
            return error
        except:
            return error

    async def change_rpc(self):
        self.logger_msg(
            self.account_name, None, msg=f'Trying to replace RPC', type_msg='warning')

        if len(self.network.rpc) != 1:
            rpcs_list = [rpc for rpc in self.network.rpc if rpc != self.rpc]
            new_rpc = random.choice(rpcs_list)
            self.w3 = AsyncWeb3(AsyncHTTPProvider(new_rpc, request_kwargs=self.request_kwargs))
            self.logger_msg(
                self.account_name, None,
                msg=f'RPC successfully replaced. New RPC: {new_rpc}', type_msg='success')
        else:
            self.logger_msg(
                self.account_name, None,
                msg=f'This network has only 1 RPC, no replacement is possible', type_msg='warning')

    def to_wei(self, number: int | float | str, decimals: int = 18) -> int:

        unit_name = {
            18: 'ether',
            6: 'mwei'
        }[decimals]

        return self.w3.to_wei(number=number, unit=unit_name)

    async def get_decimals(self, token_name: str = None, token_address: str = None) -> int:
        contract_address = token_address if token_address else TOKENS_PER_CHAIN[self.network.name][token_name]
        contract = self.get_contract(contract_address)
        return await contract.functions.decimals().call()

    async def get_normalize_amount(self, token_name: str, amount_in_wei: int) -> float:
        decimals = await self.get_decimals(token_name)
        return float(amount_in_wei / 10 ** decimals)

    async def get_smart_amount(
            self, settings: tuple = (20, 30), need_percent: bool = False, token_name: str = None
    ) -> float:
        if not token_name:
            token_name = self.token

        if isinstance(settings[0], str) or need_percent:
            _, amount, _ = await self.get_token_balance(token_name)
            percent = round(random.uniform(float(settings[0]), float(settings[1])), 6) / 100
            amount = round(amount * percent, 6)
        else:
            amount = self.round_amount(*settings)
        return amount

    async def get_token_balance(
            self, token_name: str = None, check_symbol: bool = True, omnicheck: bool = False,
            check_native: bool = False, bridge_check: bool = False, token_address: str = None
    ) -> [float, int, str]:
        if not token_name:
            token_name = self.token

        if not check_native:
            if token_name != self.network.token:
                if token_address:
                    contract = self.get_contract(token_address)
                else:
                    contract = self.get_contract(TOKENS_PER_CHAIN[self.network.name][token_name])

                amount_in_wei = await contract.functions.balanceOf(self.address).call()
                decimals = await contract.functions.decimals().call()

                if check_symbol:
                    symbol = await contract.functions.symbol().call()
                    return amount_in_wei, amount_in_wei / 10 ** decimals, symbol
                return amount_in_wei, amount_in_wei / 10 ** decimals, ''

        amount_in_wei = await self.w3.eth.get_balance(self.address)
        return amount_in_wei, amount_in_wei / 10 ** 18, self.network.token

    def get_contract(self, contract_address: str, abi: dict = ERC20_ABI) -> AsyncContract:
        return self.w3.eth.contract(
            address=AsyncWeb3.to_checksum_address(contract_address),
            abi=abi
        )

    async def get_allowance(self, token_address: str, spender_address: str) -> int:
        contract = self.get_contract(token_address)
        return await contract.functions.allowance(
            self.address,
            spender_address
        ).call()

    async def get_priotiry_fee(self) -> int:
        fee_history = await self.w3.eth.fee_history(25, 'latest', [20.0])
        non_empty_block_priority_fees = [fee[0] for fee in fee_history["reward"] if fee[0] != 0]

        divisor_priority = max(len(non_empty_block_priority_fees), 1)

        priority_fee = int(round(sum(non_empty_block_priority_fees) / divisor_priority))

        return priority_fee

    async def prepare_transaction(self, value: int = 0) -> dict:
        try:
            tx_params = {
                'chainId': self.network.chain_id,
                'from': self.w3.to_checksum_address(self.address),
                'nonce': await self.w3.eth.get_transaction_count(self.address),
                'value': value,
            }

            if self.network.eip1559_support:

                base_fee = await self.w3.eth.gas_price
                max_priority_fee_per_gas = await self.get_priotiry_fee()

                if self.network.name == 'Fantom':
                    max_priority_fee_per_gas = int(base_fee / 4)

                max_fee_per_gas = base_fee + max_priority_fee_per_gas

                tx_params['maxPriorityFeePerGas'] = max_priority_fee_per_gas
                tx_params['maxFeePerGas'] = max_fee_per_gas
                tx_params['type'] = '0x2'
            else:
                if self.network.name == 'BNB Chain':
                    tx_params['gasPrice'] = self.w3.to_wei(round(random.uniform(1.2, 1.5), 1), 'gwei')
                else:
                    tx_params['gasPrice'] = await self.w3.eth.gas_price

            return tx_params
        except Exception as error:
            raise BlockchainException(f'{self.get_normalize_error(error)}')

    async def make_approve(self, token_address: str, spender_address: str, amount_in_wei: int) -> bool:
        transaction = await self.get_contract(token_address).functions.approve(
            spender_address,
            amount=2 ** 256 - 1
        ).build_transaction(await self.prepare_transaction())

        return await self.send_transaction(transaction)

    async def check_for_approved(self, token_address: str, spender_address: str, amount_in_wei: int,
                                 without_bal_check: bool = False) -> bool:
        try:
            contract = self.get_contract(token_address)

            balance_in_wei = await contract.functions.balanceOf(self.address).call()
            symbol = await contract.functions.symbol().call()

            self.logger_msg(*self.acc_info, msg=f'Check for approval {symbol}')

            if not without_bal_check and balance_in_wei <= 0:
                raise SoftwareException(f'Zero {symbol} balance')

            approved_amount_in_wei = await self.get_allowance(
                token_address=token_address,
                spender_address=spender_address
            )

            if amount_in_wei <= approved_amount_in_wei:
                self.logger_msg(*self.acc_info, msg=f'Already approved')
                return False

            result = await self.make_approve(token_address, spender_address, amount_in_wei)

            await sleep(random.randint(5, 9))
            return result
        except Exception as error:
            raise BlockchainException(f'{self.get_normalize_error(error)}')

    async def send_transaction(
            self, transaction, need_hash: bool = False, without_gas: bool = False, poll_latency: int = 10,
            timeout: int = 360
    ) -> bool | HexStr:
        try:
            if not without_gas:
                transaction['gas'] = int((await self.w3.eth.estimate_gas(transaction)) * 1.5)
        except Exception as error:
            raise BlockchainException(f'{self.get_normalize_error(error)}')

        try:
            singed_tx = self.w3.eth.account.sign_transaction(transaction, self.private_key)
            tx_hash = self.w3.to_hex(await self.w3.eth.send_raw_transaction(singed_tx.rawTransaction))
        except Exception as error:
            if self.get_normalize_error(error) == 'already known':
                self.logger_msg(*self.acc_info, msg='RPC got error, but tx was send', type_msg='warning')
                return True
            else:
                raise BlockchainException(f'{self.get_normalize_error(error)}')

        total_time = 0
        timeout = timeout if self.network.name != 'Polygon' else 1200

        while True:
            try:
                receipts = await self.w3.eth.get_transaction_receipt(tx_hash)
                status = receipts.get("status")
                if status == 1:
                    message = f'Transaction was successful: {self.explorer}tx/{tx_hash}'
                    self.logger_msg(*self.acc_info, msg=message, type_msg='success')
                    if need_hash:
                        return tx_hash
                    return True
                elif status is None:
                    await asyncio.sleep(poll_latency)
                else:
                    self.logger_msg(*self.acc_info, msg=f'Transaction failed: {self.explorer}tx/{tx_hash}',
                                    type_msg='error')
                    return False
            except TransactionNotFound:
                if total_time > timeout:
                    if self.network.name in ['BNB Chain', 'Moonbeam']:
                        self.logger_msg(
                            *self.acc_info,
                            msg=f'Transaction was sent and tried to be confirmed, but not finished yet',
                            type_msg='warning')
                        return True
                    raise TimeExhausted(f"Transaction is not in the chain after {timeout} seconds")
                total_time += poll_latency
                await asyncio.sleep(poll_latency)

            except Exception as error:
                self.logger_msg(*self.acc_info, msg=f'RPC got autims response. Error: {error}', type_msg='warning')
                total_time += poll_latency
                await asyncio.sleep(poll_latency)

    async def get_token_price(self, token_name: str, vs_currency: str = 'usd') -> float:
        await asyncio.sleep(2)  # todo поправить на 10с
        url = 'https://api.coingecko.com/api/v3/simple/price'

        params = {'ids': f'{token_name}', 'vs_currencies': f'{vs_currency}'}

        async with self.session.get(url, params=params) as response:
            if response.status == 200:
                data = await response.json()
                return float(data[token_name][vs_currency])
            elif response.status == 429:
                self.logger_msg(
                    *self.acc_info, msg=f'CoinGecko API got rate limit. Next try in 60 second', type_msg='warning')
                await asyncio.sleep(60)
            raise SoftwareException(f'Bad request to CoinGecko API: {response.status}')

