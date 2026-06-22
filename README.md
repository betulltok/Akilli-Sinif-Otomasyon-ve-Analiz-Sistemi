# Akıllı Sınıf Otomasyon ve Analiz Sistemi

## Proje Hakkında

Bu proje, akıllı sınıf ortamını dijital ikiz yaklaşımıyla modelleyen bir simülasyon sistemidir.

Sistem içerisinde;

* Öğrenci giriş-çıkış simülasyonu
* CO₂ seviyesi takibi
* Sıcaklık değişimi
* Akıllı aydınlatma kontrolü
* Havalandırma sistemi kontrolü
* Enerji tüketimi analizi

gerçek zamanlı olarak modellenmektedir.

Üretilen sensör verileri SQLite veritabanında saklanmakta ve Flask tabanlı REST API üzerinden sunulmaktadır.

## Kullanılan Teknolojiler

* Python
* Flask
* SQLite
* NumPy
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

docs/
```

## Simülasyonu Çalıştırma

```bash
python simulation/dijital_ikiz.py
```

## Backend API'yi Çalıştırma

```bash
python backend/app.py
```

## API Endpointleri

### Ana Sayfa

```http
GET /
```

### Sensör Verileri

```http
GET /api/data
```

Son 50 sensör kaydını JSON formatında döndürür.

## Geliştiriciler


