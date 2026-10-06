"""SİMURG referans mimarisi.

Bu paket, docs/ altında anlatılan mimarinin uçuş-kritik algoritmalarının
çalıştırılabilir referans modellerini içerir. Gerçek uçuş yazılımı değildir;
algoritmaların davranışını doğrulamak, gereksinimleri test etmek ve
dijital ikiz için "altın model" (golden model) olarak kullanılmak üzere
tasarlanmıştır.
"""

import logging

__version__ = "0.2.0"

# Kütüphane varsayılan olarak terminale yazmaz; uygulama logging'i yapılandırır.
logging.getLogger(__name__).addHandler(logging.NullHandler())
