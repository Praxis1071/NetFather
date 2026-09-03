"""
NetFather TUI (Text User Interface) paketi.

`python -m netfather` (parametresiz) çalıştırıldığında açılan interaktif
terminal arayüzü burada uygulanır.

Bu paket, mevcut CLI'nin kullandığı aynı `manager`/`network`/`core`
katmanlarını kullanır; hiçbir iş mantığını tekrar etmez, doğrudan
veritabanı sorgusu veya subprocess çağrısı yapmaz. TUI yalnızca bu
katmanların bir kullanıcı arayüzüdür.

Modüller:
    state.py   Rich'ten bağımsız, saf durum/navigasyon mantığı.
    data.py    Ekranlar için veri toplama (mevcut manager/network/core
               fonksiyonlarını çağıran ince sarmalayıcılar).
    render.py   Rich tabanlı görsel oluşturma fonksiyonları.
    terminal.py Terminal capability detection ve portable klavye girişi.
    app.py      Ana döngü: ekran güncelleme ve terminal yönetimi.
"""

from __future__ import annotations
