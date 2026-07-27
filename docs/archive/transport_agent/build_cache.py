import time
# 載入 time 模組，用來讓程式暫停（sleep）

import json
# 載入 json 模組，用來把字典存成 .json 檔案

import requests
# 載入 requests 模組，用來發送 HTTP 請求給 API

import os
# 載入 os 模組，用來讀取環境變數

from dotenv import load_dotenv
load_dotenv()
# 讀取 .env 檔案裡的金鑰，載入成環境變數

TDX_CLIENT_ID     = os.getenv("TDX_CLIENT_ID")
TDX_CLIENT_SECRET = os.getenv("TDX_CLIENT_SECRET")
# 從環境變數取出 TDX 的帳號密碼

def get_tdx_token():
    url = "https://tdx.transportdata.tw/auth/realms/TDXConnect/protocol/openid-connect/token"
    response = requests.post(url, data={
        "grant_type":    "client_credentials",
        "client_id":     TDX_CLIENT_ID,
        "client_secret": TDX_CLIENT_SECRET
    })
    return response.json().get("access_token", "")
# 向 TDX 換取臨時通行證（Token）
# 每次呼叫 API 前都需要這個 Token

headers = {
    "Accept": "application/json",
    "Authorization": f"Bearer {get_tdx_token()}"
}
# 建立 HTTP 請求的標頭
# Accept → 告訴 API 我要 JSON 格式的回應
# Authorization → 帶上 Token 證明身份

print("正在取得台北市停車路段清單...")
url_taipei = (
    "https://tdx.transportdata.tw/api/basic/v1/Parking/OnStreet/"
    "ParkingSegmentAvailability/City/Taipei?%24format=JSON"
)
# TDX 台北市路邊停車 API 網址
# %24 是 $ 的 URL 編碼

response_taipei = requests.get(url_taipei, headers=headers, timeout=10)
# 發送 GET 請求給 TDX API
# timeout=10 → 等最多 10 秒，超過就放棄

items_taipei = response_taipei.json().get("CurbParkingSegmentAvailabilities", [])
# 把回傳的 JSON 轉成 Python 字典
# 取出 CurbParkingSegmentAvailabilities 這個欄位（路段清單）
# 如果沒有這個欄位就用空清單 []

print(f"台北市共 {len(items_taipei)} 個路段")
# 印出台北市有幾個路段
# len() 計算清單長度

print("正在取得新北市停車路段清單...")
url_newtaipei = (
    "https://tdx.transportdata.tw/api/basic/v1/Parking/OnStreet/"
    "ParkingSegmentAvailability/City/NewTaipei?%24format=JSON"
)
# 同樣的 API，但城市換成 NewTaipei

response_newtaipei = requests.get(url_newtaipei, headers=headers, timeout=10)
items_newtaipei = response_newtaipei.json().get("CurbParkingSegmentAvailabilities", [])
print(f"新北市共 {len(items_newtaipei)} 個路段")

items = items_taipei + items_newtaipei
# 用 + 把兩個清單合併成一個
# 例如 [1,2] + [3,4] = [1,2,3,4]

names = list(set([
    item.get("ParkingSegmentName", {}).get("Zh_tw", "")
    for item in items
]))
# 這是「列表推導式」，等於一個 for 迴圈
# 逐一取出每個路段的中文名稱
# set() → 去除重複的名稱（有些路段名稱可能一樣）
# list() → 把 set 轉回清單，因為 set 不能用 enumerate

print(f"去除重複後共 {len(names)} 個路段名稱，開始查座標...")

coords = {}
# 建立一個空字典，用來存路段名稱和對應的座標
# 格式：{ "中山北路1段53巷": {"lat": 25.04, "lon": 121.52} }

for i, name in enumerate(names):
    # enumerate() → 同時取得索引 i 和內容 name
    # 例如 i=0, name="中山北路1段53巷"
    # i=1, name="中山北路2段27巷" ...

    if not name:
        continue
    # 如果名稱是空字串就跳過，繼續下一個

    geo_url = "https://nominatim.openstreetmap.org/search"
    # Nominatim 是 OpenStreetMap 的免費地理編碼服務
    # 可以把地名轉成經緯度

    geo_params = {
        "q":      name + " 台灣",
        # 搜尋關鍵字，加上「台灣」避免找到其他國家的同名地點
        "format": "json",
        # 要求回傳 JSON 格式
        "limit":  1
        # 只要第一筆最相關的結果
    }

    geo_headers = {"User-Agent": "TransportApp/1.0"}
    # Nominatim 規定一定要加 User-Agent，不然會被擋

    try:
        res      = requests.get(geo_url, params=geo_params,
                                headers=geo_headers, timeout=5)
        geo_data = res.json()
        # 發送請求並把結果轉成 Python 字典

        if geo_data:
            # 如果有找到結果
            coords[name] = {
                "lat": float(geo_data[0]["lat"]),
                "lon": float(geo_data[0]["lon"])
            }
            # 把座標存進字典
            # float() 把文字型態的數字轉成真正的小數
            # 例如 "25.0478" → 25.0478
            print(f"[{i+1}/{len(names)}] ✅ {name}")
        else:
            print(f"[{i+1}/{len(names)}] ❌ {name} 查不到")
            # 查不到就印出錯誤，但繼續跑下一個

    except Exception as e:
        print(f"[{i+1}/{len(names)}] ❌ {name} 錯誤：{e}")
        # 發生任何錯誤（網路斷線、逾時等）就印出錯誤訊息

    time.sleep(1)
    # 每查完一個就等 1 秒
    # Nominatim 免費版規定每秒最多 1 個請求，太快會被擋

with open("coords.json", "w", encoding="utf-8") as f:
    json.dump(coords, f, ensure_ascii=False, indent=2)
# open("coords.json", "w") → 開啟檔案準備寫入
# "w" → write 模式，如果檔案存在就覆蓋掉
# encoding="utf-8" → 用 UTF-8 編碼，中文才能正常儲存
# json.dump() → 把 Python 字典寫入檔案
# ensure_ascii=False → 中文直接存，不轉成 \uXXXX 編碼
# indent=2 → 每層縮排 2 個空格，讓檔案格式化好閱讀

print(f"\n完成！共 {len(coords)} 個座標存入 coords.json")
# 最後印出總共存了幾個座標