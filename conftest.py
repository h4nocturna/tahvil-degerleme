"""pytest yapılandırması: proje kökünü sys.path'e ekler.

Böylece testler hangi çalışma dizininden koşulursa koşulsun
``import bond_lab`` sorunsuz çalışır.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
