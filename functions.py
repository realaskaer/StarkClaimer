from modules import *
from utils.networks import *
from settings import (GLOBAL_NETWORK)


def get_client(account_number, private_key, network, proxy, bridge_from_evm:bool = False) -> Client | StarknetClient:
    if GLOBAL_NETWORK != 9 or bridge_from_evm:
        return Client(account_number, private_key, network, proxy)
    return StarknetClient(account_number, private_key, network, proxy)


def get_network_by_chain_id(chain_id):
    return {
        1: ArbitrumRPC,
        2: Arbitrum_novaRPC,
        3: BaseRPC,
        4: LineaRPC,
        5: MantaRPC,
        6: PolygonRPC,
        7: OptimismRPC,
        8: ScrollRPC,
        9: StarknetRPC,
        10: Polygon_ZKEVM_RPC,
        11: zkSyncEraRPC,
        12: ZoraRPC,
        13: EthereumRPC,
        14: AvalancheRPC,
        15: BSC_RPC,
        16: MoonbeamRPC,
        17: HarmonyRPC,
        18: TelosRPC,
        19: CeloRPC,
        20: GnosisRPC,
        21: CoreRPC,
        22: TomoChainRPC,
        23: ConfluxRPC,
        24: OrderlyRPC,
        25: HorizenRPC,
        26: MetisRPC,
        27: AstarRPC,
        28: OpBNB_RPC,
        29: MantleRPC,
        30: MoonriverRPC,
        31: KlaytnRPC,
        32: KavaRPC,
        33: FantomRPC,
        34: AuroraRPC,
        35: CantoRPC,
        36: DFK_RPC,
        37: FuseRPC,
        38: GoerliRPC,
        39: MeterRPC,
        40: OKX_RPC,
        41: ShimmerRPC,
        42: TenetRPC,
        43: XPLA_RPC,
        44: LootChainRPC,
        45: ZKFairRPC
    }[chain_id]


def get_key_by_id_from(args, chain_from_id):
    private_keys = args[0].get('stark_key'), args[0].get('evm_key')
    current_key = private_keys[1]
    if chain_from_id == 9:
        current_key = private_keys[0]
    return current_key


async def claim_evm(account_number, private_key, network, proxy):
    worker = ClaimerEVM(Client(account_number, private_key, network, proxy))
    return await worker.claim_strk_tokens()


# async def claim_starknet(account_number, private_key, _, proxy):
#     network = StarknetRPC
#     worker = ClaimerStarknet(StarknetClient(account_number, private_key, network, proxy))
#     return await worker.claim_strk_tokens()


async def claim_starknet(account_number, private_key, _, proxy):
    network = StarknetRPC
    worker = ClaimerStarknet(StarknetClient(account_number, private_key, network, proxy))
    return await worker.claim_onchain()


async def transfer_strk(account_number, private_key, _, proxy):
    network = StarknetRPC
    worker = Starknet(StarknetClient(account_number, private_key, network, proxy))
    return await worker.transfer_strk()


async def collect_from_sub_okx(account_number, private_key, network, proxy):
    worker = OKX(Client(account_number, private_key, network, proxy))
    return await worker.transfer_from_subs()


async def collect_from_sub_binance(account_number, private_key, network, proxy):
    worker = Binance(Client(account_number, private_key, network, proxy))
    return await worker.transfer_from_subs()
