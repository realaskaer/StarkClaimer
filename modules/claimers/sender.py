from modules import Logger
from modules.interfaces import SoftwareExceptionWithoutRetry
from utils.tools import helper
from config import TOKENS_PER_CHAIN


class Starknet(Logger):
    def __init__(self, client):
        self.client = client
        Logger.__init__(self)

    @helper
    async def transfer_strk(self):
        await self.client.initialize_account()

        try:
            with open('./data/services/cex_withdraw_list.json') as file:
                from json import load
                cex_withdraw_list = load(file)
        except:
            self.logger_msg(None, None, f"Bad data in cex_withdraw_list.json", 'error')

        try:
            cex_wallet = cex_withdraw_list[self.client.account_name]
        except Exception as error:
            raise SoftwareExceptionWithoutRetry(f'There is no wallet listed for deposit to CEX: {error}')

        amount_in_wei, amount, _ = await self.client.get_token_balance(token_name='STRK')

        self.logger_msg(*self.client.acc_info, msg=f'Transfer {amount} STRK to {cex_wallet}')

        transfer_call = self.client.prepare_call(
            contract_address=TOKENS_PER_CHAIN['Starknet']['STRK'],
            selector_name="transfer",
            calldata=[
                int(cex_wallet, 16),
                amount_in_wei, 0
            ]
        )

        return await self.client.send_transaction(transfer_call)
