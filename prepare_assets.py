"""Verify the bundled, licensed assets. No downloads or personal paths."""
from pathlib import Path
import hashlib

ROOT = Path(__file__).resolve().parent
ASSETS = ROOT / 'assets'
EXPECTED = {'bongocat.gif': '1fba455dbbf57507f8021fa49ce7ebb1d4a6973f0f1b5a760ad60e473befddf4', 'logo.svg': '96c994d6a0a494dae69fb0fd2305c7ae515b82d48e2fd965cb11faabd8de916c', 'm3shapes-LICENSE.txt': '5f97625b2145a917b270c2d402727a6989a6a9e7bc51c34e40ede8ea888a1a48', 'MaterialSymbols-LICENSE.txt': '58d1e17ffe5109a7ae296caafcadfdbe6a7d176f0bc4ab01e12a689b0499d8bd', 'MaterialSymbolsRounded.ttf': '32e4011709e055596eb8d2dd0f7cb547b47c1d40ac9ecb8fad54f7f7eac202e7', 'Rubik-OFL.txt': '472cbe7c25441df63e9c7864b43eb3c0f4b3df950c66a76224e6cfe1eae843fb', 'Rubik.ttf': '1b3a7437ba2af80e465e773ed60c5036d1ba6ace492d89046dbcf18fb31e4e88'}

def main():
    for name, expected in EXPECTED.items():
        path = ASSETS / name
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise SystemExit('Asset missing or modified: ' + name)
        print('OK', name)

if __name__ == '__main__':
    main()
