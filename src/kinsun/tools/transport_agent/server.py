import os
import json
import math
import requests
# os       → 讀取環境變數（API 金鑰）
# json     → 讀取 coords.json 座標檔案
# math     → 計算距離用的數學函式
# requests → 發送 HTTP 請求給 TDX API

from flask import Flask, jsonify, request
# Flask   → 建立網頁伺服器
# jsonify → 把 Python 字典轉成 JSON 格式回傳給網頁
# request → 讀取網頁傳來的參數（例如 lat、lon）

from flask_cors import CORS
# CORS → 允許 map.html 跨網域存取這個伺服器
# 沒有這行，瀏覽器會擋住 map.html 的請求

from dotenv import load_dotenv
load_dotenv()
# 讀取 .env 檔案裡的金鑰，載入成環境變數

TDX_CLIENT_ID     = os.getenv("TDX_CLIENT_ID")
TDX_CLIENT_SECRET = os.getenv("TDX_CLIENT_SECRET")
# 從環境變數取出 TDX 的帳號和密碼

# ── 取得 TDX Token ────────────────────────────────────────────
def get_tdx_token():
    """向 TDX 換取臨時通行證（Token）"""
    url = "https://tdx.transportdata.tw/auth/realms/TDXConnect/protocol/openid-connect/token"
    response = requests.post(url, data={
        "grant_type":    "client_credentials",
        # 固定填這個，表示用帳號密碼換 Token
        "client_id":     TDX_CLIENT_ID,
        # 你的 TDX 帳號
        "client_secret": TDX_CLIENT_SECRET
        # 你的 TDX 密碼
    })
    return response.json().get("access_token", "")
    # 從回傳的 JSON 取出 access_token
    # 如果沒有就回傳空字串

# ── 載入座標檔案 ──────────────────────────────────────────────
with open("coords.json", "r", encoding="utf-8") as f:
    coords_cache = json.load(f)
# open("coords.json", "r") → 開啟 coords.json 檔案（讀取模式）
# encoding="utf-8"         → 用 UTF-8 編碼，讓中文正常顯示
# json.load(f)             → 把檔案內容轉成 Python 字典

print(f"✅ 已載入 {len(coords_cache)} 個座標")
# 程式啟動時顯示載入了幾個座標，確認檔案有正常讀取

# ── 查詢座標函式 ──────────────────────────────────────────────
def get_coords(name):
    """從 coords_cache 取得路段的經緯度"""
    data = coords_cache.get(name)
    # 直接從字典查，瞬間完成，不需要網路請求
    # coords_cache 格式：{ "路段名稱": {"lat": 25.xxx, "lon": 121.xxx} }

    if data:
        return (data["lat"], data["lon"])
        # 回傳 (緯度, 經度) 的 tuple

    return None
    # 如果這個路段不在檔案裡，回傳 None

# ── 計算距離函式 ──────────────────────────────────────────────
def calc_distance(lat1, lon1, lat2, lon2):
    """
    用 Haversine 公式計算兩個經緯度之間的距離（公尺）
    這是計算地球表面兩點距離的標準公式
    """
    R = 6371000
    # 地球半徑，單位是公尺

    φ1 = math.radians(lat1)
    φ2 = math.radians(lat2)
    # math.radians() → 把角度轉成弧度
    # 三角函數需要用弧度，不能直接用角度

    Δφ = math.radians(lat2 - lat1)
    Δλ = math.radians(lon2 - lon1)
    # Δ（Delta）表示兩點的差值

    a = (math.sin(Δφ/2) ** 2 +
         math.cos(φ1) * math.cos(φ2) * math.sin(Δλ/2) ** 2)
    # Haversine 公式的核心計算

    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    # atan2 是反正切函數，用來計算角度

    return R * c
    # 回傳距離，單位是公尺

# ── 建立 Flask 伺服器 ─────────────────────────────────────────
app = Flask(__name__)
# Flask(__name__) → 建立伺服器物件
# __name__ 是 Python 內建變數，代表這個檔案的名稱

CORS(app)
# 允許所有來源的網頁存取這個伺服器
# 沒有這行，map.html 發送請求時瀏覽器會擋住

# ── 附近停車格 API ────────────────────────────────────────────
@app.route('/parking/nearby')
# @app.route 是「裝飾器」
# 當有人訪問 http://localhost:5000/parking/nearby 時，執行下面的函式
def get_nearby_parking():
    """接收經緯度，回傳附近的路邊停車格即時資訊"""

    lat    = request.args.get('lat', type=float)
    lon    = request.args.get('lon', type=float)
    radius = request.args.get('radius', default=3000, type=int)
    # request.args.get() → 取出網址 ? 後面的參數
    # 例如 ?lat=25.033&lon=121.564&radius=3000
    # type=float  → 自動把文字轉成小數
    # type=int    → 自動把文字轉成整數
    # default=3000 → 如果沒有傳 radius，預設搜尋 3000 公尺

    if not lat or not lon:
        return jsonify({"error": "請提供 lat 和 lon 參數"}), 400
    # 如果沒有提供座標就回傳錯誤
    # 400 是 HTTP 狀態碼，代表「你的請求有問題」

    # 建立 TDX 請求標頭
    tdx_headers = {
        "Accept": "application/json",
        # 告訴 API 我要 JSON 格式的回應
        "Authorization": f"Bearer {get_tdx_token()}"
        # 帶上 Token 證明身份
    }

    # 取台北市即時停車資料
    url_tp = (
        "https://tdx.transportdata.tw/api/basic/v1/Parking/OnStreet/"
        "ParkingSegmentAvailability/City/Taipei?%24format=JSON"
    )
    res_tp   = requests.get(url_tp, headers=tdx_headers, timeout=10)
    # 發送 GET 請求，timeout=10 表示等最多 10 秒
    items_tp = res_tp.json().get("CurbParkingSegmentAvailabilities", [])
    # 取出台北市停車路段清單，沒有就用空清單

    # 取新北市即時停車資料
    url_ntpc = (
        "https://tdx.transportdata.tw/api/basic/v1/Parking/OnStreet/"
        "ParkingSegmentAvailability/City/NewTaipei?%24format=JSON"
    )
    res_ntpc   = requests.get(url_ntpc, headers=tdx_headers, timeout=10)
    items_ntpc = res_ntpc.json().get("CurbParkingSegmentAvailabilities", [])
    # 取出新北市停車路段清單

    items = items_tp + items_ntpc
    # 用 + 把兩個清單合併成一個
    # 例如 [台北市資料] + [新北市資料] = [全部資料]

    # 逐一篩選出附近的停車格
    results = []
    # 建立空清單，之後把符合條件的停車格加進來

    for item in items:
        name      = item.get("ParkingSegmentName", {}).get("Zh_tw", "未知")
        # 取出路段的中文名稱
        available = item.get("AvailableSpaces", -1)
        # 剩餘車位數，-1 表示感應器無資料
        total     = item.get("TotalSpaces", 0)
        # 總車位數

        coords = get_coords(name)
        # 從 coords_cache 查這個路段的座標

        if coords:
            # 只有查到座標才繼續處理
            parking_lat, parking_lon = coords
            # 把座標拆成緯度和經度

            distance = calc_distance(lat, lon, parking_lat, parking_lon)
            # 計算這個停車格距離搜尋點多遠（公尺）

            if distance <= radius:
                # 只保留在指定半徑範圍內的停車格
                results.append({
                    "name":      name,
                    "available": available,
                    "total":     total,
                    "lat":       parking_lat,
                    "lon":       parking_lon,
                    "distance":  round(distance)
                    # round() 把距離四捨五入成整數公尺
                })

    results.sort(key=lambda x: x["distance"])
    # 按距離由近到遠排序
    # lambda x: x["distance"] → 用 distance 欄位來排序

    return jsonify(results)
    # 把結果轉成 JSON 格式回傳給 map.html

# ── 載入 Gemini ───────────────────────────────────────────────
from google import genai
from google.genai import types
# 載入 Google Gemini AI 套件

GEMINI_KEY = os.getenv("GEMINI_API_KEY")
# 從環境變數取出 Gemini 的 API 金鑰

gemini_client = genai.Client(api_key=GEMINI_KEY)
# 建立 Gemini 客戶端，之後用這個發問題給 AI

# ── 四個交通工具函式（給 Gemini 使用）────────────────────────
def get_google_route(origin: str, destination: str) -> dict:
    """查詢兩地之間的路線距離和開車時間"""

    def get_coordinates(place_name: str):
        # 把地名轉成經緯度
        url = "https://nominatim.openstreetmap.org/search"
        params = {"q": place_name + " 台灣", "format": "json", "limit": 1}
        headers = {"User-Agent": "TransportAgent/1.0"}
        res  = requests.get(url, params=params, headers=headers)
        data = res.json()
        if data:
            return float(data[0]["lon"]), float(data[0]["lat"])
        return None, None

    origin_lon, origin_lat = get_coordinates(origin)
    dest_lon,   dest_lat   = get_coordinates(destination)

    if not origin_lat or not dest_lat:
        return {"錯誤": "找不到地點座標"}

    url = (
        f"http://router.project-osrm.org/route/v1/driving/"
        f"{origin_lon},{origin_lat};{dest_lon},{dest_lat}?overview=false"
    )
    # 用 OSRM 免費路線 API 計算距離和時間
    res  = requests.get(url, timeout=10)
    data = res.json()

    if data.get("code") == "Ok":
        route        = data["routes"][0]
        distance_km  = round(route["distance"] / 1000, 1)
        duration_min = round(route["duration"] / 60, 0)
        return {
            "出發地":   origin,
            "目的地":   destination,
            "距離":     f"{distance_km} 公里",
            "開車時間": f"{int(duration_min)} 分鐘"
        }
    return {"錯誤": "路線計算失敗"}


def get_taipei_bus(route_name: str) -> dict:
    """查詢台北市公車路線的即時到站資訊"""
    url = (
        f"https://tdx.transportdata.tw/api/basic/v2/Bus/EstimatedTimeOfArrival/"
        f"City/Taipei/{route_name}?%24top=10&%24format=JSON"
    )
    tdx_headers = {
        "Accept": "application/json",
        "Authorization": f"Bearer {get_tdx_token()}"
    }
    response = requests.get(url, headers=tdx_headers, timeout=10)

    if response.status_code == 200:
        data    = response.json()
        results = []
        for item in data[:5]:
            eta = item.get("EstimatedTime")
            if eta is not None:
                eta_text = f"約 {round(eta / 60)} 分鐘後"
            else:
                eta_text = "即將到站或無資料"
            results.append({
                "站名":     item.get("StopName", {}).get("Zh_tw", "未知"),
                "預計到站": eta_text
            })
        if results:
            return {"公車路線": route_name, "到站資訊": results}

    return {"錯誤": f"無法取得 {route_name} 路線資料"}


def get_taipei_mrt(station_name: str) -> dict:
    """查詢台北捷運站所在的路線"""
    url = (
        "https://tdx.transportdata.tw/api/basic/v2/Rail/Metro/"
        "StationOfRoute/TRTC?%24top=30&%24format=JSON"
    )
    tdx_headers = {
        "Accept": "application/json",
        "Authorization": f"Bearer {get_tdx_token()}"
    }
    response = requests.get(url, headers=tdx_headers)

    if response.status_code == 200:
        data     = response.json()
        matching = [
            r for r in data
            if any(
                station_name in s.get("StationName", {}).get("Zh_tw", "")
                for s in r.get("Stations", [])
            )
        ]
        if matching:
            route = matching[0]
            return {
                "路線名稱": route.get("RouteName", {}).get("Zh_tw", "未知"),
                "查詢站名": station_name,
                "說明":     "請至台北捷運官網查看最新時刻表"
            }

    return {"錯誤": f"找不到 {station_name} 的捷運資訊"}


def get_parking_info(city: str = "taipei") -> dict:
    """查詢台北市或新北市路邊停車即時空位"""
    if city == "taipei":
        url = (
            "https://tdx.transportdata.tw/api/basic/v1/Parking/OnStreet/"
            "ParkingSegmentAvailability/City/Taipei?%24top=10&%24format=JSON"
        )
    else:
        url = (
            "https://tdx.transportdata.tw/api/basic/v1/Parking/OnStreet/"
            "ParkingSegmentAvailability/City/NewTaipei?%24top=10&%24format=JSON"
        )

    tdx_headers = {
        "Accept": "application/json",
        "Authorization": f"Bearer {get_tdx_token()}"
    }
    response = requests.get(url, headers=tdx_headers, timeout=10)

    if response.status_code == 200:
        data  = response.json()
        items = data.get("CurbParkingSegmentAvailabilities", [])
        if items:
            results = []
            for item in items[:5]:
                results.append({
                    "路段名稱": item.get("ParkingSegmentName", {}).get("Zh_tw", "未知"),
                    "總車位":   item.get("TotalSpaces", "?"),
                    "剩餘車位": item.get("AvailableSpaces", "?")
                })
            return {"城市": "台北市" if city == "taipei" else "新北市",
                    "停車資訊": results}

    return {"錯誤": "無法取得停車資料"}


# ── AI 問答 API ───────────────────────────────────────────────
@app.route('/ask', methods=['POST'])
# methods=['POST'] → 這個路由只接受 POST 請求
# POST 用來傳送資料，GET 只是讀取

def ask_agent():
    """接收使用者問題，交給 Gemini 回答"""

    data     = request.get_json()
    # request.get_json() → 取出前端傳來的 JSON 資料

    question = data.get('question', '')
    lang     = data.get('lang', 'zh-TW')
    # 前端傳來的語言，例如 'zh-TW' 或 'en-US'
    # 讓 AI 知道使用者用什麼語言問問題

    if not question:
        return jsonify({"error": "請輸入問題"}), 400
    # 問題是空的就直接回傳錯誤

    try:
        tools_for_gemini = [
            get_google_route,
            get_taipei_bus,
            get_taipei_mrt,
            get_parking_info,
        ]
        # 把四個交通工具函式傳給 Gemini

        if lang == 'en-US':
            # 使用者選英語，用英文系統提示
            system_prompt = (
                "You are a professional transportation assistant for Taipei and New Taipei City. "
                "When the user asks about routes, you MUST use get_google_route, get_taipei_mrt, and get_taipei_bus tools "
                "to find driving, MRT, and bus information, then compare and recommend the best option. "
                "You MUST reply in the following exact format:\n\n"
                "===中文===\n"
                "（用繁體中文寫相同內容）\n\n"
                "===英文===\n"
                "🚇 MRT: (route and transfer info, estimated time)\n"
                "🚌 Bus: (route numbers, estimated time)\n"
                "🚗 Drive: (distance and time)\n"
                "✅ Recommendation: (recommended option and reason)\n\n"
                "Always include BOTH ===中文=== and ===英文=== sections. Never skip either section."
            )
        else:
            # 使用者選國語或台語，用中文系統提示
            system_prompt = (
                "你是台北和新北市的專業交通助理。"
                "當使用者問路線時，你必須同時使用 get_google_route、get_taipei_mrt、get_taipei_bus 這三個工具。"
                "你必須同時回傳兩個版本的回答，格式如下：\n\n"
                "===中文===\n"
                "🚇 捷運：（路線和換乘說明，預估時間）\n"
                "🚌 公車：（可搭的路線號碼，預估時間）\n"
                "🚗 開車：（距離和時間）\n"
                "✅ 推薦：（推薦哪種方式，說明理由）\n\n"
                "===英文===\n"
                "🚇 MRT: (route and transfer info, estimated time)\n"
                "🚌 Bus: (route numbers, estimated time)\n"
                "🚗 Drive: (distance and time)\n"
                "✅ Recommendation: (recommended option and reason)\n\n"
                "請嚴格遵守格式，一定要有 ===中文=== 和 ===英文=== 兩個區塊。"
            )


        response = gemini_client.models.generate_content(
            model="gemini-3.1-flash-lite",
            contents=question,
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
                tools=tools_for_gemini,
                automatic_function_calling=types.AutomaticFunctionCallingConfig(
                    disable=False
                ),
            ),
        )

        # ── 把中文和英文回答拆開 ──────────────────────────────
        full_text = response.text
        # Gemini 的完整回答

        zh_text = full_text
        en_text = full_text
        # 預設兩個都是完整回答

        zh_text = full_text
        # 中文回答就是完整回答

        if '===中文===' in full_text and '===英文===' in full_text:
            parts   = full_text.split('===英文===')
            zh_text = parts[0].replace('===中文===', '').strip()
            en_text = parts[1].strip()
        else:
            # 不管有沒有格式，只要是英語模式就直接翻譯
            if lang == 'en-US':
                translate_response = gemini_client.models.generate_content(
                    model="gemini-3.1-flash-lite",
                    contents=(
                        "Translate this Chinese transportation information to natural English. "
                        "Keep emojis. Output English only, no Chinese:\n\n"
                        + full_text
                    ),
                )
                en_text = translate_response.text.strip()
            else:
                en_text = full_text

        # ── 解析目的地座標 ────────────────────────────────────
        dest_lat, dest_lon = None, None
        # 常見英文地名對照中文，避免 Nominatim 找錯地方
        name_map = {
            "xingtian temple":    "行天宮",
            "sing tien temple":   "行天宮",
            "taipei 101":         "台北101",
            "taipei main station": "台北車站",
            "ximending":          "西門町",
            "ximen":              "西門町",
            "shilin night market": "士林夜市",
            "jiufen":             "九份",
            "danshui":            "淡水",
            "tamsui":             "淡水",
            "tamsui old street":  "淡水老街",
            "longshan temple":    "龍山寺",
            "chiang kai-shek memorial": "中正紀念堂",
            "beitou":             "北投",
            "zhongshan":          "中山",
            "songshan":           "松山",
            "neihu":              "內湖",
            "nangang":            "南港",
            "muzha":              "木柵",
            "shida":              "師大",
            "gongguan":           "公館",
            "yongkang street":    "永康街",
            "dihua street":       "迪化街",
            "raohe night market": "饒河夜市",
            "ningxia night market": "寧夏夜市",
            "daan park":          "大安森林公園",
            "da an park":         "大安森林公園",
            "national palace museum": "國立故宮博物院",
            "elephant mountain":  "象山",
            "maokong":            "貓空",
            "wulai":              "烏來",
            "pingxi":             "平溪",
        }
        # 字典格式：英文名稱 → 中文名稱
        # 查到中文後用中文搜尋座標，結果更準確

        try:
            keywords    = ["到", "去", "前往", "抵達", " to ", " To "]
            # 加上英文的 to，注意前後有空格避免誤判
            destination = None
            for kw in keywords:
                if kw in question:
                    parts_q = question.split(kw)
                    # 用關鍵字把問題切開
                    if len(parts_q) > 1:
                        destination = parts_q[-1].strip()
                        destination = (destination
                            .replace("怎麼去", "")
                            .replace("？", "")
                            .replace("?", "")
                            .replace("how do I get", "")
                            .replace("how to get", "")
                            .strip())
                        # 清除多餘的字，只留地點名稱
                        break

            if destination:
                geo_url = "https://nominatim.openstreetmap.org/search"
                # 檢查目的地是否有英文對照
                dest_lower = destination.lower().strip()
                # lower() 轉小寫，方便比對
                if dest_lower in name_map:
                    destination = name_map[dest_lower]
                    # 找到對照就換成中文名稱
                geo_res = requests.get(geo_url, params={
                    "q":      destination + " 台灣",
                    "format": "json",
                    "limit":  1
                }, headers={"User-Agent": "TransportApp/1.0"}, timeout=5)
                geo_data = geo_res.json()
                if geo_data:
                    dest_lat = float(geo_data[0]["lat"])
                    dest_lon = float(geo_data[0]["lon"])
                    # 查到座標就存起來，之後傳給地圖
        except:
            pass
            # 查不到座標也沒關係，地圖不跳轉就好

        return jsonify({
            "answer":    zh_text,
            # 中文回答，顯示在對話框裡
            "answer_en": en_text,
            # 英文回答，選英語時朗讀用
            "dest_lat":  dest_lat,
            "dest_lon":  dest_lon
            # 目的地座標，讓地圖自動跳轉
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500
        # 如果發生任何錯誤，回傳錯誤訊息




# ── 程式入口 ──────────────────────────────────────────────────
if __name__ == "__main__":
    app.run(port=5000, debug=True)
    # port=5000  → 伺服器跑在 5000 這個埠號
    # debug=True → 程式碼改變時自動重啟，開發時很方便