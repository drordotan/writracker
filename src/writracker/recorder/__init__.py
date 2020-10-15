import os

from . import dataio
from . import results


if os.name == 'nt':
    from . import wintab
    from . import wintab_params
    from . import recorder
