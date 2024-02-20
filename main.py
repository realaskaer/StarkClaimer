import asyncio
import sys

from config import TITLE
from termcolor import cprint
from questionary import Choice, select
from utils.modules_runner import Runner
from utils.route_generator import RouteGenerator
from utils.tools import create_okx_withdrawal_list


def main():
    cprint(TITLE, 'light_cyan')
    cprint(f'\n❤️ My channel for latest updates: https://t.me/askaer\n', 'light_green', attrs=["blink"])

    while True:
        answer = select(
            'What do you want to do?',
            choices=[
                Choice("🚀 Start running the machine", 'classic_routes_run'),
                Choice("📄 Generate classic-route", 'classic_routes_gen'),
                Choice("💾 Create and safe OKX withdrawal file", 'create_okx_list'),
                Choice("✅ Check the connection of each proxy", 'check_proxy'),
                Choice('❌ Exit', "exit")
            ],
            qmark='🛠️',
            pointer='👉'
        ).ask()

        runner = Runner()

        if answer == 'check_proxy':
            print()
            asyncio.run(runner.check_proxies_status())
            print()
        elif answer == 'classic_routes_run':
            print()
            asyncio.run(runner.run_accounts())
            print()
        elif answer == 'create_okx_list':
            print()
            create_okx_withdrawal_list()
            print()
        elif answer == 'classic_routes_gen':
            generator = RouteGenerator()
            generator.classic_routes_json_save()
        elif answer == 'exit':
            sys.exit()
        else:
            print()
            answer()
            print()


if __name__ == "__main__":
    main()
