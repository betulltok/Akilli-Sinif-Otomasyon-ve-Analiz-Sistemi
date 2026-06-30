# -*- coding: utf-8 -*-
"""
Created on Thu Mar 12 10:30:22 2026
@author: arvasis (Modified for Recycling Bin, Small Items & Slower Fill Rate)
@updated: Sensör sınıfları datasheet tabanlı modellerle güncellendi (HC-SR04, MQ135, MLX90614, ACS712-benzeri)
"""

import numpy as np
import heapq
from collections import deque
import math
import sqlite3
import os

# simulation/dijital_ikiz.py -> proje kökü
PROJE_KOKU = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


###############
## KUTUPHANE ##
###############
class TimeLine:
    def __init__(self):
        self.data = {}  
        self.heap = []    

    def add(self, event):
        index = event.time
        if index not in self.data:
            self.data[index] = deque()
            heapq.heappush(self.heap, index)
        self.data[index].append(event)

    def pop(self):
        while self.heap:
            time = self.heap[0]
            if time not in self.data:
                heapq.heappop(self.heap)
                continue
            queue = self.data[time]
            event = queue.popleft()
            if not queue:
                del self.data[time]
                heapq.heappop(self.heap)
            return time, event
        return None, "Koleksiyon tamamen boş!"
    
    def clear(self):
        self.data = {}  
        self.heap = [] 

class SimulationEvent:
    def __init__(self, name, timeLine, time, parameters, procedure):
        self.name = name
        self.procedure = procedure
        self.time = time
        self.timeLine = timeLine
        self.parameters = parameters
        
    def run(self):
        if self.procedure:
            time = self.procedure(self.timeLine, self.time, self.parameters)
        else:
            time = self.time
        return time


# --- GERİ DÖNÜŞÜM EVENTLERİ ---
class TrashThrownEvent(SimulationEvent):
    def __init__(self, timeLine, time, parameters, procedure):
        super().__init__("TrashThrown", timeLine, time, parameters, procedure)

class TrashFallingEvent(SimulationEvent):
    def __init__(self, timeLine, time, parameters, procedure):
        super().__init__("TrashFalling", timeLine, time, parameters, procedure)

class TrashHitGroundEvent(SimulationEvent):
    def __init__(self, timeLine, time, parameters, procedure):
        super().__init__("TrashHitGround", timeLine, time, parameters, procedure)

class EmptyBinEvent(SimulationEvent):
    def __init__(self, timeLine, time, parameters, procedure):
        super().__init__("EmptyBin", timeLine, time, parameters, procedure)


# --- ÇEVRE VE İNSAN EVENTLERİ ---
class ArrivalEvent(SimulationEvent):
    def __init__(self, timeLine, time, parameters, procedure):
        super().__init__("Arrival", timeLine, time, parameters, procedure)

class DepartureEvent(SimulationEvent):
    def __init__(self, timeLine, time, parameters, procedure, agent):
        super().__init__("Departure", timeLine, time, parameters, procedure)
        self.agent = agent 
        
    def run(self):
        if self.procedure:
            time = self.procedure(self.timeLine, self.time, self.parameters, self.agent)
        else:
            time = self.time
        return time

class EnvironmentUpdateEvent(SimulationEvent):
    def __init__(self, timeLine, time, parameters, procedure):
        super().__init__("EnvUpdate", timeLine, time, parameters, procedure)


###################################
## SENSÖR SINIFLARI (DATASHEET)  ##
###################################
class Sensor:
    def __init__(self, name, tolerance):
        self.name = name
        self.tolerance = tolerance


class UltrasonicSensor(Sensor):
    """
    HC-SR04 datasheet referansları:
      - Ölçüm aralığı: 2 cm - 400 cm (bu aralık dışında güvenilir değil)
      - Çözünürlük: ~0.3 cm (datasheet 'resolution: 0.3 cm')
      - Doğruluk: ±3 mm (sabit gürültü payı, mesafeden bağımsız)
      - Ses hızı sıcaklığa bağlıdır: v(T) = 331.3 + 0.606*T (m/s),
        bu yüzden ortam sıcaklığı değiştiğinde ham TOF ölçümünde sistematik hata oluşur.
    """
    def __init__(self, ambient_temp=22.0):
        super().__init__(name="HC-SR04", tolerance=0.003)  # ±3mm
        self.min_range = 0.02     # 2 cm - blind zone altı
        self.max_range = 4.00     # 400 cm - menzil üstü
        self.resolution = 0.003   # ~0.3 cm quantization adımı
        self.ambient_temp = ambient_temp

    @staticmethod
    def _speed_of_sound(temp_c):
        return 331.3 + 0.606 * temp_c

    def capture(self, true_distance, ambient_temp=None):
        temp = ambient_temp if ambient_temp is not None else self.ambient_temp

        # Sensör, sesin hızını sabit (kalibre edildiği) sıcaklıkta varsayar.
        # Gerçek ortam sıcaklığı farklıysa TOF->mesafe çevrimi sistematik hata içerir.
        calibration_temp = 22.0
        nominal_speed = self._speed_of_sound(calibration_temp)
        actual_speed = self._speed_of_sound(temp)
        speed_error_factor = actual_speed / nominal_speed

        measured = true_distance * speed_error_factor
        measured += np.random.normal(0, self.tolerance)  # datasheet ±3mm gürültü

        if measured < self.min_range:
            # Blind zone: sensör bu aralıkta güvenilir okuma veremez
            return 0.0
        if measured > self.max_range:
            return self.max_range

        # ADC/zamanlayıcı çözünürlüğüne göre kuantize et
        measured = round(measured / self.resolution) * self.resolution
        return max(0.0, measured)


class CO2Sensor(Sensor):
    """
    MQ135 datasheet referansları:
      - Yarı-logaritmik Rs/Ro - ppm karakteristiği: ppm ≈ a * (Rs/Ro)^b
        (datasheet eğrisinden yaklaşık fit: a≈116.6, b≈-2.77)
      - Isınma süresi (preheat) gereklidir; ısınmadan önce ölçümler kararsız/sapmalıdır.
      - Sıcaklık ve nem, sensör direncini (Rs) etkiler, bu yüzden datasheet
        sıcaklık/nem düzeltme eğrileri önerir.
    """
    def __init__(self, warmup_time=60.0):
        super().__init__(name="MQ135", tolerance=15.0)
        self.warmup_time = warmup_time
        self.elapsed_time = 0.0
        self.is_warmed_up = False
        # datasheet eğrisinden yaklaşık fit parametreleri
        self.curve_a = 116.6020682
        self.curve_b = -2.769034857

    def update_warmup(self, dt):
        if not self.is_warmed_up:
            self.elapsed_time += dt
            if self.elapsed_time >= self.warmup_time:
                self.is_warmed_up = True

    def capture(self, true_co2, temperature=22.0, humidity=50.0):
        if not self.is_warmed_up:
            # Isınma tamamlanmadan ölçümler düşük/kararsız çıkar (datasheet notu)
            return max(400.0, true_co2 * np.random.uniform(0.5, 0.8))

        # Sıcaklık/nem düzeltme katsayıları (datasheet karakteristik eğrisinden yaklaşık)
        temp_correction = 1.0 + 0.005 * (temperature - 22.0)
        humidity_correction = 1.0 - 0.002 * (humidity - 50.0)
        corrected = true_co2 * temp_correction * humidity_correction

        measured = corrected + np.random.normal(0, self.tolerance)
        return max(400.0, measured)


class TemperatureSensor(Sensor):
    """
    MLX90614 datasheet referansları:
      - Çözünürlük: 0.02°C
      - Doğruluk: ±0.5°C (0..50°C aralığında tipik)
      - Çıkış gürültüsü datasheette verilen doğruluk değerinden türetilmiştir.
    """
    def __init__(self):
        super().__init__(name="MLX90614", tolerance=0.5)  # datasheet ±0.5°C
        self.resolution = 0.02  # datasheet çözünürlüğü

    def capture(self, true_temp):
        # Doğruluk değeri "maksimum hata" olduğundan std sapmayı biraz daha düşük tutuyoruz
        measured = true_temp + np.random.normal(0, self.tolerance / 2.0)
        measured = round(measured / self.resolution) * self.resolution
        return measured


class CurrentSensor(Sensor):
    """
    ACS712-benzeri akım sensörü karakteristiği:
      - Kazanç (sensitivity) hatası: datasheette tipik ±1.5%
      - Sıfır nokta (offset) kayması: sıcaklık/üretim toleransından kaynaklanır
      - Çıkış gürültüsü (datasheet noise referansı)
    """
    def __init__(self, sensitivity_error=0.015, offset_drift=0.02):
        super().__init__(name="Current_Sensor", tolerance=0.05)
        self.sensitivity_error = sensitivity_error  # ±%1.5 tipik
        self.offset_drift = offset_drift            # A

    def capture(self, true_current):
        gain_error = 1.0 + np.random.uniform(-self.sensitivity_error, self.sensitivity_error)
        offset = np.random.normal(0, self.offset_drift)
        measured = true_current * gain_error + offset
        measured += np.random.normal(0, self.tolerance)
        return max(0.0, measured)


###################################
## AJAN (AGENT) SINIFLARI        ##
###################################
class Agent:
    def __init__(self, agent_id):
        self.agent_id = agent_id

class OccupantAgent(Agent):
    def __init__(self, agent_id, x, y):
        super().__init__(agent_id)
        self.x = x
        self.y = y
        self.co2_emission_rate = 0.03 

    def emit(self, interval):
        return self.co2_emission_rate * interval

class SmartLightAgent(Agent):
    def __init__(self, agent_id, wattage=60.0):
        super().__init__(agent_id)
        self.wattage = wattage
        self.is_on = False

    def consume(self, interval):
        if self.is_on:
            return self.wattage * (interval / 3600.0)
        return 0.0

class VentilationAgent(Agent):
    """
    PID kontrollü değişken hızlı havalandırma.
    fan_speed: 0-100 arası, PID çıkışıyla belirlenir.
    Güç tüketimi ve tahliye hızı fan_speed ile orantılı (basit lineer fan modeli).
    """
    def __init__(self, agent_id, wattage=1000.0, evacuation_rate=10.0):
        super().__init__(agent_id)
        self.wattage = wattage
        self.evacuation_rate = evacuation_rate
        self.fan_speed = 0.0   # %0-100
        self.is_on = False     # geriye uyumluluk / raporlama için

    def consume(self, interval):
        fraction = self.fan_speed / 100.0
        return self.wattage * fraction * (interval / 3600.0)

    def evacuate(self, interval):
        fraction = self.fan_speed / 100.0
        return self.evacuation_rate * fraction * interval


#############################
## KONTROL ALGORİTMALARI   ##
#############################
class PIDController:
    """
    Basit PID kontrolcü. CO2 seviyesini setpoint'e çekmek için
    fan hızını (%0-100) hesaplar.
    error = measured_value - setpoint  (CO2 setpoint'in üstündeyse pozitif -> fan hızlanır)
    Anti-windup: integral terimi çıkış limitlerine göre clamp edilir.
    """
    def __init__(self, kp, ki, kd, setpoint, output_min=0.0, output_max=100.0):
        self.kp = kp
        self.ki = ki
        self.kd = kd
        self.setpoint = setpoint
        self.output_min = output_min
        self.output_max = output_max
        self.integral = 0.0
        self.prev_error = None

    def reset(self):
        self.integral = 0.0
        self.prev_error = None

    def update(self, measured_value, dt):
        if dt <= 0:
            dt = 1e-6

        error = measured_value - self.setpoint

        self.integral += error * dt
        # Anti-windup: integral'i çıkış aralığıyla orantılı sınırla
        max_integral = self.output_max / max(self.ki, 1e-9) if self.ki > 0 else 0.0
        if self.ki > 0:
            self.integral = max(-max_integral, min(max_integral, self.integral))

        if self.prev_error is None:
            derivative = 0.0
        else:
            derivative = (error - self.prev_error) / dt
        self.prev_error = error

        output = self.kp * error + self.ki * self.integral + self.kd * derivative
        output = max(self.output_min, min(self.output_max, output))
        return output


#############################
## ENERJİ FİYATLANDIRMA    ##
#############################
def get_energy_price(simTime):
    """
    Basit zaman dilimli (time-of-use) tarife modeli.
    Gün, simülasyon başlangıcını 08:00 kabul ederek saatlere bölünür.
    - Puant (peak) saatler   : 11:00-13:00 ve 17:00-20:00 -> yüksek tarife
    - Gündüz (normal) saatler: 08:00-11:00, 13:00-17:00   -> orta tarife
    - Gece/diğer              : geri kalan                -> düşük tarife
    Birim: TL/kWh (örnek değerler, gerçek tarifeyle değiştirilebilir)
    """
    sim_start_hour = 8
    hour_of_day = (sim_start_hour + simTime / 3600.0) % 24

    if (11 <= hour_of_day < 13) or (17 <= hour_of_day < 20):
        return 3.50  # puant tarife
    elif (8 <= hour_of_day < 11) or (13 <= hour_of_day < 17):
        return 2.20  # gündüz tarifesi
    else:
        return 1.40  # gece tarifesi



def capture_and_classify():
    print("   [KAMERA] -> captured image (Biri geri dönüşüm kutusuna pet şişe/ambalaj attı, sınıflandırılıyor...)")


###########################
## DEGISKEN & PARAMETRELER##
###########################

smart_lights = [SmartLightAgent(agent_id=f"Light_{i+1}", wattage=60.0) for i in range(4)]
ventilation_system = VentilationAgent(agent_id="HVAC_1", wattage=1000.0, evacuation_rate=10.0)

simParameters = {
    'SimulationDuration': 28800.0,   
    'EnvUpdateInterval': 60.0,       
    
    'TotalArrivalsPlanned': 200,     
    'ArrivalsSoFar': 0,
    'ActiveOccupants': [],           
    'RoomWidth': 8.0,
    'RoomLength': 6.0,
    
    # GERİ DÖNÜŞÜM KUTUSU VE FİZİK
    'BinHeight': 0.8,                # Standart geri dönüşüm kutusu boyutu (80 cm)
    'Gravity': 9.81,             
    'TrashInterval': 0.05,            
    'BinSensor': UltrasonicSensor(ambient_temp=22.0),
    'StartTime': 0.0,            
    'CurrentTrashInBin': 0,
    'TotalTrashDroppedDay': 0,       
    'TrashThickness': 0.02,          # Pet şişe, kağıt ambalaj gibi atıkların ezilmiş kalınlığı (2 cm)
    'MaxBinCapacity': 40,            # 0.8m / 0.02m = 40 adet atık kapasitesi
    
    'TrueCO2': 400.0,
    'TrueHumidity': 50.0,
    'CriticalCO2Level': 1200.0,          
    'SafeCO2Level': 400.0,               
    'BaseTemp': 22.0,                    
    'TempPerPerson': 0.15,               
    'GridVoltage': 220.0,                
    'TotalEnergy_Wh': 0.0,               
    
    'Lights': smart_lights,
    'LightHysteresisState': [False, False, False, False],  # her ışığın mevcut açık/kapalı durumu (histerezis için)
    'Ventilation': ventilation_system,
    'HVAC_PID': PIDController(kp=0.08, ki=0.002, kd=0.01, setpoint=800.0, output_min=0.0, output_max=100.0),
    'CO2Sensor': CO2Sensor(warmup_time=60.0),
    'TempSensor': TemperatureSensor(),
    'CurrentSensor': CurrentSensor(),
    'TotalEnergyCost_TL': 0.0
}

simParameters['ArrivalRate'] = simParameters['SimulationDuration'] / simParameters['TotalArrivalsPlanned']
simulationTimeLine = TimeLine()

# =====================================================
# SQLITE VERITABANI BAGLANTISI
# =====================================================

conn = sqlite3.connect(os.path.join(PROJE_KOKU, "database", "smart_classroom.db"))
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS sensor_data (
    time REAL,
    co2 REAL,
    temperature REAL,
    current REAL,
    energy REAL,
    people INTEGER,
    trash_count INTEGER
)
""")

conn.commit()

#######################
## MODEL PROSEDÜRLERİ##
#######################

# 1. GERİ DÖNÜŞÜM KUTUSU PROSEDÜRLERİ
def trashThrownProcedure(timeLine, simTime, params):
    if params['CurrentTrashInBin'] >= params['MaxBinCapacity']:
        print(f"   [{simTime:.1f} sn] -> UYARI: Geri dönüşüm kutusu zaten dolu, atılan atık taştı!")
        
    capture_and_classify()
    params['StartTime'] = simTime 
    next_check = simTime + params['TrashInterval']
    timeLine.add(TrashFallingEvent(timeLine, round(next_check, 4), params, trashFallingProcedure))
    return simTime

def trashFallingProcedure(timeLine, simTime, params):
    t = simTime - params['StartTime']
    distance_fallen = 0.5 * params['Gravity'] * (t ** 2)
    current_height = params['BinHeight'] - distance_fallen
    
    current_trash_level = params['CurrentTrashInBin'] * params['TrashThickness']
    effective_drop_height = params['BinHeight'] - current_trash_level
    
    if effective_drop_height <= 0:
        effective_drop_height = 0.001 
        
    total_falling_time = math.sqrt((2 * effective_drop_height) / params['Gravity'])
    
    if t >= total_falling_time or current_height <= current_trash_level:
        exact_hit_time = params['StartTime'] + total_falling_time
        timeLine.add(TrashHitGroundEvent(timeLine, round(exact_hit_time, 4), params, trashHitGroundProcedure))
        return simTime

    # Ortam sıcaklığını sensöre ilet (HC-SR04 ses hızı sıcaklık bağımlılığı için)
    params['BinSensor'].capture(distance_fallen, ambient_temp=params['BaseTemp'])
    next_check = simTime + params['TrashInterval']
    timeLine.add(TrashFallingEvent(timeLine, round(next_check, 4), params, trashFallingProcedure))
    return simTime

def trashHitGroundProcedure(timeLine, simTime, params):
    params['CurrentTrashInBin'] += 1
    params['TotalTrashDroppedDay'] += 1
    
    current_trash_level = params['CurrentTrashInBin'] * params['TrashThickness']
    
    print(f"   [{simTime:.1f} sn] -> Çöp atıldı. Yığın Yüksekliği: {current_trash_level:.2f}m (Kutudaki: {params['CurrentTrashInBin']}/{params['MaxBinCapacity']})")
    
    if params['CurrentTrashInBin'] >= params['MaxBinCapacity']:
        empty_time = simTime + 10.0
        timeLine.add(EmptyBinEvent(timeLine, round(empty_time, 2), params, emptyBinProcedure))
        
    return simTime

def emptyBinProcedure(timeLine, simTime, params):
    print(f"\n   [{simTime:.1f} sn] -> [GERİ DÖNÜŞÜM GÖREVLİSİ] Kutu boşaltıldı!\n")
    params['CurrentTrashInBin'] = 0
    return simTime


# 2. İNSAN HAREKETLERİ (GELİŞ VE AYRILIŞ)
def arrivalProcedure(timeLine, simTime, params):
    agent_id = f"Person_{params['ArrivalsSoFar'] + 1}"
    x = np.random.uniform(0, params['RoomWidth'])
    y = np.random.uniform(0, params['RoomLength'])
    
    new_occupant = OccupantAgent(agent_id, x, y)
    params['ActiveOccupants'].append(new_occupant)
    
    if np.random.rand() < 0.30:
        trash_time = simTime + np.random.uniform(2.0, 10.0)
        timeLine.add(TrashThrownEvent(timeLine, round(trash_time, 2), params, trashThrownProcedure))
    
    stay_duration = np.random.uniform(1800, 7200) 
    leave_time = simTime + stay_duration
    if leave_time <= params['SimulationDuration']:
        timeLine.add(DepartureEvent(timeLine, round(leave_time, 2), params, departureProcedure, new_occupant))

    params['ArrivalsSoFar'] += 1
    if params['ArrivalsSoFar'] < params['TotalArrivalsPlanned']:
        next_arrival = simTime + np.random.exponential(params['ArrivalRate'])
        if next_arrival < params['SimulationDuration']:
            timeLine.add(ArrivalEvent(timeLine, round(next_arrival, 2), params, arrivalProcedure))
            
    return simTime

def departureProcedure(timeLine, simTime, params, agent):
    if agent in params['ActiveOccupants']:
        params['ActiveOccupants'].remove(agent)
    return simTime


# 3. ÇEVRESEL VE ENERJİ ÖLÇÜM PROSEDÜRÜ
def environmentUpdateProcedure(timeLine, simTime, params):
    num_people = len(params['ActiveOccupants'])
    interval = params['EnvUpdateInterval']
    
    co2_emitted = sum(agent.emit(interval) for agent in params['ActiveOccupants'])
    params['TrueCO2'] += co2_emitted
    
    true_temp = params['BaseTemp'] + (num_people * params['TempPerPerson'])

    # --- HVAC: PID KONTROLÜ ---
    # Setpoint'in üstünde fan hızlanır, altında yavaşlar/durur (sürekli ayar, ani aç/kapa yok)
    vent = params['Ventilation']
    pid = params['HVAC_PID']
    fan_speed = pid.update(params['TrueCO2'], interval)
    vent.fan_speed = fan_speed
    vent.is_on = fan_speed > 0.5  # raporlama amaçlı

    if vent.fan_speed > 0:
        co2_evacuated = vent.evacuate(interval)
        params['TrueCO2'] = max(400.0, params['TrueCO2'] - co2_evacuated)

    # --- IŞIKLAR: HİSTEREZİSLİ EŞİK KONTROLÜ ---
    # Her ışık katmanı için ayrı ON/OFF eşiği var; aradaki boşluk (gap) flicker'ı önler.
    # i. ışık ON eşiği : (i*10)+1 kişi,  OFF eşiği: i*10 - 2 kişi (negatifse 0)
    for i, light in enumerate(params['Lights']):
        on_threshold = (i * 10) + 1
        off_threshold = max(0, (i * 10) - 2)
        currently_on = params['LightHysteresisState'][i]

        if not currently_on and num_people >= on_threshold:
            params['LightHysteresisState'][i] = True
        elif currently_on and num_people <= off_threshold:
            params['LightHysteresisState'][i] = False

        light.is_on = params['LightHysteresisState'][i]

    active_lights_needed = sum(1 for s in params['LightHysteresisState'] if s)

    lights_energy = sum(light.consume(interval) for light in params['Lights'])
    vent_energy = vent.consume(interval)
    interval_energy_wh = lights_energy + vent_energy
    params['TotalEnergy_Wh'] += interval_energy_wh

    # --- ENERJİ FİYATLANDIRMA ---
    price_per_kwh = get_energy_price(simTime)
    interval_cost_tl = (interval_energy_wh / 1000.0) * price_per_kwh
    params['TotalEnergyCost_TL'] += interval_cost_tl

    active_power_w = active_lights_needed * 60.0 + vent.wattage * (vent.fan_speed / 100.0)

    true_current_a = active_power_w / params['GridVoltage']
    
    # MQ135 ısınma süresini ilerlet (datasheet: preheat tamamlanmadan kararlı ölçüm yok)
    params['CO2Sensor'].update_warmup(interval)

    measured_current = params['CurrentSensor'].capture(true_current_a)
    measured_co2 = params['CO2Sensor'].capture(
        params['TrueCO2'], temperature=true_temp, humidity=params['TrueHumidity']
    )
    measured_temp = params['TempSensor'].capture(true_temp)

    # =====================================================
    # SENSOR VERILERINI VERITABANINA KAYDET
    # =====================================================

    cursor.execute("""
    INSERT INTO sensor_data
    VALUES (?, ?, ?, ?, ?, ?, ?)
    """,
    (
        simTime,
        measured_co2,
        measured_temp,
        measured_current,
        params['TotalEnergy_Wh'],
        num_people,
        params['CurrentTrashInBin']
    ))

    conn.commit()

    if simTime > 0 and simTime % 3600 == 0:
        saat = int(simTime // 3600)
        price_now = get_energy_price(simTime)
        
        print(f"\n[{saat}. SAAT RAPORU | Zaman: {simTime:.0f}s] ---")
        print(f"  * Odadaki Aktif İnsan: {num_people}")
        print(f"  * Işık Durumu: {active_lights_needed} Işık Açık (histerezisli)")
        print(f"  * Havalandırma Durumu: Fan Hızı %{vent.fan_speed:.1f} (PID kontrollü)")
        print(f"  * MQ135 Isınma Durumu: {'TAMAMLANDI' if params['CO2Sensor'].is_warmed_up else 'ISINIYOR'}")
        print(f"  * Anlık Akım (Şebeke Çekişi): {measured_current:.3f}A")
        print(f"  * Toplam Enerji Tüketimi: {params['TotalEnergy_Wh']:.2f} Wh")
        print(f"  * Güncel Tarife: {price_now:.2f} TL/kWh | Toplam Maliyet: {params['TotalEnergyCost_TL']:.2f} TL")
        print(f"  * Sensörler -> Sıcaklık: {measured_temp:.2f}°C | CO2: {measured_co2:.0f} ppm")
        print("--------------------------------------")
    
    next_update = simTime + interval
    if next_update <= params['SimulationDuration']:
        timeLine.add(EnvironmentUpdateEvent(timeLine, round(next_update, 2), params, environmentUpdateProcedure))
        
    return simTime


######################
## SIMÜLASYON RUN ##
######################

print("--- 8 SAATLİK GERÇEKÇİ FİZİK VE ABM-DES HİBRİT SİMÜLASYONU BAŞLIYOR ---\n")

simulationTimeLine.add(ArrivalEvent(simulationTimeLine, 0.0, simParameters, arrivalProcedure))
simulationTimeLine.add(EnvironmentUpdateEvent(simulationTimeLine, simParameters['EnvUpdateInterval'], simParameters, environmentUpdateProcedure))

# Event Döngüsü
while len(simulationTimeLine.data) > 0:
    time, event = simulationTimeLine.pop()
    event.run()

print("\n--- SİMÜLASYON TAMAMLANDI ---")
print(f"Gün Sonu Geri Dönüşüm Kutusunda Kalan Atık Sayısı: {simParameters['CurrentTrashInBin']}")
print(f"Gün İçinde Atılan TOPLAM Atık Sayısı: {simParameters['TotalTrashDroppedDay']}")
print(f"Gün Sonu Toplam Enerji Tüketimi: {simParameters['TotalEnergy_Wh']:.2f} Wh")
print(f"Gün Sonu Toplam Enerji Maliyeti: {simParameters['TotalEnergyCost_TL']:.2f} TL")

# =====================================================
# VERITABANI BAGLANTISINI KAPAT
# =====================================================

conn.close()