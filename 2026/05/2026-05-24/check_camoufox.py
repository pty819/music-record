import sys
sys.path.insert(0, '/home/liyifan/.hermes/profiles/scraper/home/.local/lib/python3.11/site_packages')
from camoufox import Camoufox
print(Camoufox.__init__.__doc__)
import inspect
print(inspect.signature(Camoufox.__init__))