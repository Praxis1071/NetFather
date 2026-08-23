"""
NetFather ORM modelleri.

Bu paket, `models.base.Base`'e bağlı tüm somut model sınıflarını burada
import eder. Bunun tek amacı SQLAlchemy'nin declarative registry'sinin
her zaman eksiksiz olmasını garanti etmektir:

    - `Base.metadata.create_all()` yalnızca o ana kadar Python tarafından
      fiilen import edilmiş (ve dolayısıyla sınıf gövdesi çalıştırılıp
      Base.metadata'ya kaydolmuş) modeller için tablo oluşturur.
    - `Device` modelindeki `relationship(Mapped[list["Profile"]])` ve
      `Mapped[list["Rule"]]` gibi string forward-reference'lar, ilgili
      sınıflar (Profile, Rule) aynı registry'de kayıtlı değilse ilk ORM
      işleminde `InvalidRequestError` ile başarısız olur.

`models.base`, `models.device` gibi herhangi bir alt modül import
edildiğinde Python önce bu `__init__.py`'yi çalıştırır; bu yüzden burada
tüm modelleri import etmek, uygulamanın veya testlerin hangi sırayla
hangi modeli import ettiğinden bağımsız olarak registry'nin daima eksiksiz
olmasını sağlar.
"""

from __future__ import annotations

from models.base import Base
from models.device import Device
from models.event import Event
from models.profile import Profile
from models.rule import Rule

__all__ = ["Base", "Device", "Event", "Profile", "Rule"]
