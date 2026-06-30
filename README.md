# Akıllı Sınıf Otomasyon ve Analiz Sistemi

## Proje Hakkında
Bu proje, akıllı sınıf ortamını dijital ikiz yaklaşımıyla modelleyen bir simülasyon sistemidir.

Sistem içerisinde;
* Öğrenci giriş-çıkış simülasyonu
* CO₂ seviyesi takibi
* Sıcaklık değişimi
* Akıllı aydınlatma kontrolü (histerezisli eşik mantığı)
* Havalandırma sistemi kontrolü (PID kontrollü değişken hızlı fan)
* Enerji tüketimi ve maliyet analizi (zaman dilimli tarife)
* Geri dönüşüm kutusu doluluk takibi

gerçek zamanlı olarak modellenmektedir.

Üretilen sensör verileri SQLite veritabanında saklanmakta ve Flask tabanlı REST API üzerinden sunulmaktadır.
Basit bir web arayüzü (frontend) ile anlık değerler ve grafikler görüntülenebilmektedir.

## Kullanılan Teknolojiler
* Python
* Flask
* SQLite
* NumPy
* Chart.js (frontend grafikler için)
* Git & GitHub

## Proje Yapısı
```text
backend/
├── app.py
database/
├── smart_classroom.db
simulation/
├── dijital_ikiz.py
frontend/
├── index.html
docs/
```

## Simülasyonu Çalıştırma
Proje kökünden:
```bash
python simulation/dijital_ikiz.py
```
Simülasyon `database/smart_classroom.db` dosyasını oluşturur (yoksa) ve sensör verilerini kaydeder.

## Backend API'yi Çalıştırma
Proje kökünden:
```bash
python backend/app.py
```
Sunucu ayağa kalktıktan sonra tarayıcıdan `http://127.0.0.1:5000/` adresine gidildiğinde frontend dashboard otomatik açılır.

## API Endpointleri

### Ana Sayfa (Dashboard)
```http
GET /
```
Frontend dashboard'unu döndürür.

### Tüm Sensör Verileri
```http
GET /api/data
```
Parametreler: `limit` (varsayılan 50), `start_time`, `end_time` (simülasyon saniyesi).
Filtrelenmiş sensör kayıtlarını JSON formatında döndürür.

### En Son Ölçüm
```http
GET /api/data/latest
```
En güncel tek sensör kaydını döndürür (canlı takip için).

### CO₂ Verisi
```http
GET /api/co2
```

### Sıcaklık Verisi
```http
GET /api/temperature
```

### Akım Verisi
```http
GET /api/current
```

### Enerji Tüketimi
```http
GET /api/energy
```

### Doluluk (Kişi Sayısı)
```http
GET /api/occupancy
```

### Geri Dönüşüm Kutusu Doluluğu
```http
GET /api/trash
```

## Geliştiriciler