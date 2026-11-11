# TFmini-i CAN GUI

Windows üzerinde Benewake TFmini-i-CAN LiDAR ölçümlerini bir USB-CAN Analyzer
ile okuyup gerçek zamanlı grafik üzerinde gösteren Python uygulaması.

## Özellikler

- Anlık mesafeyi metre ve santimetre olarak gösterir.
- Son 10 saniyenin mesafe grafiğini çizer.
- Sinyal gücünü, sensör zaman damgasını ve ölçüm hızını gösterir.
- Seeed/GY tipi CH340 tabanlı USB-CAN Analyzer ile çalışır.
- TFmini-i'nin 8 baytlık CAN ölçüm çerçevesini little-endian olarak çözer.
- Terminal kullanmadan açılabilen `.pyw` başlatıcısı içerir.

## TFmini-i varsayılan CAN ayarları

| Ayar | Değer |
| --- | --- |
| CAN hızı | 250 kbit/s |
| Çerçeve | Standart, 11 bit |
| Gönderim/alım ID | `0x003` |
| Ölçüm hızı | 100 Hz |

Ölçüm çerçevesi:

| Baytlar | İçerik | Biçim |
| --- | --- | --- |
| 0–1 | Mesafe | unsigned 16 bit, little-endian, cm |
| 2–3 | Sinyal gücü | unsigned 16 bit, little-endian |
| 4–7 | Sensör zaman damgası | unsigned 32 bit, little-endian, ms |

`0xFFFF` mesafe değeri geçersiz/zayıf sinyalli ölçüm olarak değerlendirilir.

## Bağlantı

| TFmini-i kablosu | İşlev |
| --- | --- |
| Kırmızı | 7–30 V DC besleme |
| Beyaz/sarı | CAN_L |
| Yeşil | CAN_H |
| Siyah | GND |

Mavi/turuncu UART_RX ve kahverengi UART_TX kablolarını CAN bağlantısında
kullanmayın. CAN hattının iki fiziksel ucunda 120 ohm sonlandırma direnci
bulunmalıdır.

> TFmini-i'nin CAN ve RS-485 modelleri farklı donanımlardır; arayüz yazılım
> komutuyla değiştirilemez.

## Kullanılan donanım

### Besleme

Bu projede TFmini-i LiDAR'ı beslemek için **12 V DC, 1 A adaptör** kullanıldı.

### USB-CAN dönüştürücü

Projede Robotistan'dan temin edilen **USB-CAN Dönüştürücü V7** kullanıldı.
Ürün sayfasına aşağıdaki görsele veya bağlantıya tıklayarak ulaşabilirsiniz.

<p align="center">
  <a href="https://www.robotistan.com/usb-can-donusturucu-v7?language=tr&amp;h=d408da05">
    <img
      src="https://robotistan.witcdn.net/usb-to-can-bus-converter-adapter-38915-65-K.jpg"
      alt="Robotistan USB-CAN Dönüştürücü V7"
      width="520"
    >
  </a>
</p>

**Ürün bağlantısı:**
[Robotistan USB-CAN Dönüştürücü V7](https://www.robotistan.com/usb-can-donusturucu-v7?language=tr&h=d408da05)

Görsel Robotistan ürün sayfasından harici olarak yüklenmektedir ve Robotistan'a
aittir.

## Kurulum

Python 3.10 veya daha yeni bir sürüm önerilir.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

## Kullanım

Grafik arayüzü:

```powershell
python lidar_gui.py
```

Windows'ta terminal açmadan kullanmak için `TFmini_CAN_Grafik.pyw` dosyasına
çift tıklayın. Varsayılan olarak `COM4`, `250000 bit/s` ve `0x003` kullanılır.
Gerekirse değerleri arayüzden değiştirin ve **Başlat** düğmesine basın.

Ham terminal çıktısı:

```powershell
python raw_lidar.py --channel COM4 --bitrate 250000 --id 0x003
```

## Dosyalar

- `lidar_gui.py`: Tkinter tabanlı gerçek zamanlı grafik arayüzü
- `raw_lidar.py`: CAN protokol çözümleyicisi ve terminal okuyucusu
- `TFmini_CAN_Grafik.pyw`: Konsolsuz Windows başlatıcısı
- `requirements.txt`: Python bağımlılıkları

## Donanım notu

CH340 tabanlı USB-CAN Analyzer Windows'ta bir COM portu olarak görünür. Bu COM
portu yalnızca bilgisayar ile CAN adaptörü arasındaki taşıma kanalıdır. LiDAR
CAN_H ve CAN_L üzerinden CAN protokolüyle haberleşir; LiDAR'ın UART pinleri
kullanılmaz.

## Kaynak

Protokol ve bağlantı bilgileri Benewake TFmini-i User Manual içindeki CAN
iletişim bölümüne dayanmaktadır:

https://ai.benewake.com/en/resources/technical-documents/tfmini-i-user-manual/
