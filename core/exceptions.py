"""
NetFather özel exception sınıfları.

Uygulama genelinde kullanılan hata tipleri burada tanımlanır.
Her exception, hangi katmanda oluştuğunu anlamayı kolaylaştırmak için
NetFatherError taban sınıfından türetilir.
"""

from __future__ import annotations


class NetFatherError(Exception):
    """Tüm NetFather hatalarının taban sınıfı."""


class ConfigError(NetFatherError):
    """Config dosyası okunamadığında veya geçersiz olduğunda fırlatılır."""


class DatabaseError(NetFatherError):
    """Database bağlantısı veya sorgu hatalarında fırlatılır."""


class NetworkError(NetFatherError):
    """Ağ arayüzü tespiti veya keşif işlemlerinde oluşan hatalarda fırlatılır."""


class DeviceNotFoundError(NetFatherError):
    """İstenen cihaz veritabanında bulunamadığında fırlatılır."""


class RuleError(NetFatherError):
    """Kural oluşturma veya uygulama sırasında oluşan hatalarda fırlatılır."""


class ProfileError(NetFatherError):
    """Profil oluşturma veya atama sırasında oluşan hatalarda fırlatılır."""
