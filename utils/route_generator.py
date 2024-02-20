import json
import random

from utils.tools import clean_progress_file
from functions import *
from web3 import AsyncWeb3
from config import ACCOUNT_NAMES
from modules import Logger
from settings import CLASSIC_ROUTES_MODULES_USING


AVAILABLE_MODULES_INFO = {
    # module_name                       : (module name, priority, tg info, can be help module, supported network)
    claim_evm                           : (claim_evm, 3, 'Claim $STRK from EVM account', 0, [0]),
    claim_starknet                      : (claim_starknet, 3, 'Claim $STRK from Starknet account', 0, [0]),
    transfer_strk                       : (transfer_strk, 3, 'Transfer $STRK', 0, [0]),
    collect_from_sub_okx                : (collect_from_sub_okx, 3, 'Collect from OKX subAccs', 0, [0]),
    collect_from_sub_binance            : (collect_from_sub_binance, 3, 'Collect from Binance subAccs', 0, [0]),
}


def get_func_by_name(module_name, help_message:bool = False):
    for k, v in AVAILABLE_MODULES_INFO.items():
        if k.__name__ == module_name:
            if help_message:
                return v[2]
            return v[0]


class RouteGenerator(Logger):
    def __init__(self):
        super().__init__()
        self.w3 = AsyncWeb3()

    @staticmethod
    def classic_generate_route():
        route = []
        for i in CLASSIC_ROUTES_MODULES_USING:
            module_name = random.choice(i)
            if module_name is None:
                continue
            module = get_func_by_name(module_name)
            route.append(module.__name__)
        return route

    def classic_routes_json_save(self):
        clean_progress_file()
        with open('./data/services/wallets_progress.json', 'w') as file:
            accounts_data = {}
            for account_name in ACCOUNT_NAMES:
                if isinstance(account_name, str):
                    classic_route = self.classic_generate_route()
                    account_data = {
                        "current_step": 0,
                        "route": classic_route
                    }
                    accounts_data[str(account_name)] = account_data
            json.dump(accounts_data, file, indent=4)
        self.logger_msg(
            None, None,
            f'Successfully generated {len(accounts_data)} classic routes in data/services/wallets_progress.json\n',
            'success')
