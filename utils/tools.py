import io
import json
import os
import random
import asyncio
import functools
import traceback

import msoffcrypto
import pandas as pd

from getpass import getpass
from termcolor import cprint
from msoffcrypto.exceptions import DecryptionError, InvalidKeyError
from settings import (
    SLEEP_TIME_RETRY,
    MAXIMUM_RETRY,
    EXCEL_PASSWORD,
    EXCEL_PAGE_NAME
)


async def sleep(self, min_time, max_time):
    duration = random.randint(min_time, max_time)
    print()
    self.logger_msg(*self.client.acc_info, msg=f"💤 Sleeping for {duration} seconds")
    await asyncio.sleep(duration)


def get_accounts_data(page_name:str = None):
    decrypted_data = io.BytesIO()
    sheet_page_name = page_name if page_name else EXCEL_PAGE_NAME
    with open('./data/accounts_data.xlsx', 'rb') as file:
        if EXCEL_PASSWORD:
            cprint('⚔️ Enter the password degen', color='light_blue')
            password = getpass()
            office_file = msoffcrypto.OfficeFile(file)

            try:
                office_file.load_key(password=password)
            except msoffcrypto.exceptions.DecryptionError:
                cprint('\n⚠️ Incorrect password to decrypt Excel file! ⚠️\n', color='light_red', attrs=["blink"])
                raise DecryptionError('Incorrect password')

            try:
                office_file.decrypt(decrypted_data)
            except msoffcrypto.exceptions.InvalidKeyError:
                cprint('\n⚠️ Incorrect password to decrypt Excel file! ⚠️\n', color='light_red', attrs=["blink"])
                raise InvalidKeyError('Incorrect password')

            except msoffcrypto.exceptions.DecryptionError:
                cprint('\n⚠️ Set password on your Excel file first! ⚠️\n', color='light_red', attrs=["blink"])
                raise DecryptionError('Excel without password')

            office_file.decrypt(decrypted_data)

            try:
                wb = pd.read_excel(decrypted_data, sheet_name=sheet_page_name)
            except ValueError as error:
                cprint('\n⚠️ Wrong page name! ⚠️\n', color='light_red', attrs=["blink"])
                raise ValueError(f"{error}")
        else:
            try:
                wb = pd.read_excel(file, sheet_name=sheet_page_name)
            except ValueError as error:
                cprint('\n⚠️ Wrong page name! ⚠️\n', color='light_red', attrs=["blink"])
                raise ValueError(f"{error}")

        accounts_data = {}
        for index, row in wb.iterrows():
            account_name = row["Name"]
            private_key = row["Private Key"]
            proxy = row["Proxy"]
            cex_address = row['CEX address']
            accounts_data[int(index) + 1] = {
                "account_name": account_name,
                "private_key": private_key,
                "proxy": proxy,
                "cex_wallet": cex_address,
            }

        acc_name, priv_key, proxy, cex_wallet = [], [], [], []
        for k, v in accounts_data.items():
            if isinstance(v['account_name'], str):
                acc_name.append(v['account_name'])
                priv_key.append(v['private_key'])
            proxy.append(v['proxy'] if isinstance(v['proxy'], str) else None)
            cex_wallet.append(v['cex_wallet'] if isinstance(v['cex_wallet'], str) else None)

        proxy = [item for item in proxy if item is not None]
        cex_wallet = [item for item in cex_wallet if item is not None]

        return acc_name, priv_key, proxy, cex_wallet


def clean_stark_file():
    with open('./data/services/stark_data.json', 'w') as file:
        file.truncate(0)


def clean_progress_file():
    with open('./data/services/wallets_progress.json', 'w') as file:
        file.truncate(0)


def check_progress_file():
    file_path = './data/services/wallets_progress.json'

    if os.path.getsize(file_path) > 0:
        return True
    else:
        return False


def save_buy_tx(account_name, amount):
    file_path = './data/services/memcoin_buys.json'
    try:
        with open(file_path, 'r') as file:
            data = json.load(file)
    except json.JSONDecodeError:
        data = {}

    data[account_name] = {
        "amount": amount
    }

    with open(file_path, 'w') as file:
        json.dump(data, file, indent=4)


def create_okx_withdrawal_list():
    from config import ACCOUNT_NAMES, CEX_WALLETS
    okx_data = {}

    if ACCOUNT_NAMES and CEX_WALLETS:
        with open('./data/services/cex_withdraw_list.json', 'w') as file:
            for account_name, okx_wallet in zip(ACCOUNT_NAMES, CEX_WALLETS):
                okx_data[account_name] = okx_wallet
            json.dump(okx_data, file, indent=4)
        cprint('✅ Successfully added and saved CEX wallets data', 'light_blue')
        cprint('⚠️ Check all CEX deposit wallets by yourself to avoid problems', 'light_yellow', attrs=["blink"])
    else:
        cprint('❌ Put your wallets into files, before running this function', 'light_red')


def helper(func):
    @functools.wraps(func)
    async def wrapper(self, *args, **kwargs):
        from modules.interfaces import (
            PriceImpactException,BlockchainException, SoftwareException, SoftwareExceptionWithoutRetry,
            BlockchainExceptionWithoutRetry
        )

        attempts = 0
        stop_flag = False
        try:
            while attempts <= MAXIMUM_RETRY:
                try:
                    return await func(self, *args, **kwargs)
                except (PriceImpactException, BlockchainException, SoftwareException, SoftwareExceptionWithoutRetry,
                        BlockchainExceptionWithoutRetry, asyncio.exceptions.TimeoutError, ValueError) as err:
                    error = err
                    attempts += 1

                    msg = f'{error} | Try[{attempts}/{MAXIMUM_RETRY + 1}]'
                    if isinstance(error, asyncio.exceptions.TimeoutError):
                        error = 'Connection to RPC is not stable'
                        await self.client.change_rpc()
                        msg = f'{error} | Try[{attempts}/{MAXIMUM_RETRY + 1}]'

                    elif isinstance(error, SoftwareExceptionWithoutRetry):
                        stop_flag = True
                        msg = f'{error}'

                    elif isinstance(error, (BlockchainException, BlockchainExceptionWithoutRetry)):

                        if any([i in str(error) for i in ['insufficient funds', 'gas required']]):
                            stop_flag = True
                            network_name = self.client.network.name
                            msg = f'Insufficient funds on {network_name}, software will stop this action\n'
                        elif 'execution reverted' in str(error):
                            stop_flag = True
                            network_name = self.client.network.name
                            msg = f'Contract execution reverted on {network_name}, software will stop this action\n'
                        else:
                            if isinstance(error, BlockchainExceptionWithoutRetry):
                                stop_flag = True
                                msg = f'{error}'

                            self.logger_msg(
                                self.client.account_name,
                                None, msg=f'Maybe problem with node: {self.client.rpc}', type_msg='warning')
                            await self.client.change_rpc()

                    self.logger_msg(self.client.account_name, None, msg=msg, type_msg='error')

                    if stop_flag:
                        break

                    if attempts > MAXIMUM_RETRY:
                        self.logger_msg(self.client.account_name,
                                        None, msg=f"Tries are over, software will stop module\n", type_msg='error')
                    else:
                        await sleep(self, *SLEEP_TIME_RETRY)

                except Exception as error:
                    msg = f'Unknown Error. Description: {error}'
                    self.logger_msg(self.client.account_name, None, msg=msg, type_msg='error')
                    traceback.print_exc()
                    break
        finally:
            await self.client.session.close()
        return False
    return wrapper

