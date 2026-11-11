"""간편 실행용: python check.py 문서.pdf -o report.html"""

import sys

from imgcheck.__main__ import main

if __name__ == "__main__":
    sys.exit(main())
