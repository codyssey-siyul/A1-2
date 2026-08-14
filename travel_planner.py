from dotenv import load_dotenv
import os
import argparse
from datetime import datetime
from google import genai
import json
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from pathlib import Path
from urllib.error import HTTPError, URLError

load_dotenv()


# ============================================================
# API 키 설정
# ============================================================

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
KAKAO_REST_API_KEY = os.getenv("KAKAO_REST_API_KEY")


# API 키 미설정 확인
if not GEMINI_API_KEY:
    print("오류: GEMINI_API_KEY가 설정되지 않았습니다.")
    print(".env 파일에 GEMINI_API_KEY를 설정해주세요.")
    raise SystemExit(1)

if not KAKAO_REST_API_KEY:
    print("오류: KAKAO_REST_API_KEY가 설정되지 않았습니다.")
    print(".env 파일에 KAKAO_REST_API_KEY를 설정해주세요.")
    raise SystemExit(1)


# Gemini 클라이언트 생성
client = genai.Client(api_key=GEMINI_API_KEY)


# ============================================================
# 1차 여행 추천 - Gemini
# ============================================================

def get_travel_recommendation(date, errors):

    prompt = f"""
{date}에 여행할 국내 여행지를 1곳 추천해주세요.

반드시 아래 JSON 형식으로만 답변해주세요.
마크다운 코드 블록(```)이나 추가 설명을 절대 포함하지 마세요.

{{
  "recommended_city": "추천 도시 이름",
  "weather": "해당 시기의 일반적인 날씨 요약",
  "events": [
    "행사 또는 축제 후보 1",
    "행사 또는 축제 후보 2"
  ],
  "reason": "추천 근거를 2~4문장으로 작성"
}}

조건:
- recommended_city는 문자열(string)입니다.
- weather는 문자열(string)입니다.
- events는 문자열(string)로 이루어진 배열(array)입니다.
- events는 1~3개만 작성합니다.
- reason은 문자열(string)이며 추천 근거를 2~4문장으로 작성합니다.
- 모든 내용은 한국어로 작성합니다.
"""

    try:
        response = client.models.generate_content(
            model="gemini-3.5-flash-lite",
            contents=prompt
        )

        print("\n===== Gemini 원본 응답 =====")
        print(response.text)

    except Exception as e:
        print("\n===== Gemini API 오류 =====")
        print(e)

        errors.append(f"Gemini API 오류: {str(e)}")
        return None


    # --------------------------------------------------------
    # JSON 파싱 1차 시도
    # --------------------------------------------------------

    try:
        travel_data = json.loads(response.text)

        required_keys = [
            "recommended_city",
            "weather",
            "events",
            "reason"
        ]

        for key in required_keys:
            if key not in travel_data:
                raise ValueError(f"필수 키 누락: {key}")

        if not isinstance(travel_data["recommended_city"], str):
            raise ValueError("recommended_city 타입 오류")

        if not isinstance(travel_data["weather"], str):
            raise ValueError("weather 타입 오류")

        if not isinstance(travel_data["events"], list):
            raise ValueError("events 타입 오류")

        if not isinstance(travel_data["reason"], str):
            raise ValueError("reason 타입 오류")

        print("\n===== JSON 파싱 성공 =====")
        print(f"추천 도시: {travel_data['recommended_city']}")
        print(f"날씨: {travel_data['weather']}")
        print(f"행사: {travel_data['events']}")
        print(f"추천 이유: {travel_data['reason']}")

        return travel_data

    except (json.JSONDecodeError, ValueError, TypeError) as e:

        print("\n===== JSON 파싱 실패 =====")
        print(e)
        print("JSON 형식으로 다시 요청합니다.")


    # --------------------------------------------------------
    # JSON 파싱 실패 → 1회 재시도
    # --------------------------------------------------------

    retry_prompt = f"""
이전 응답을 JSON으로 파싱할 수 없었습니다.

{date} 국내 여행 추천 정보를 아래 JSON 형식으로만 다시 출력해주세요.
설명, 마크다운, 코드 블록은 절대 포함하지 마세요.

{{
  "recommended_city": "추천 도시 이름",
  "weather": "해당 시기의 일반적인 날씨 요약",
  "events": ["행사 또는 축제 후보 1"],
  "reason": "추천 근거 2~4문장"
}}

필수 키는 반드시 다음 4개입니다.

recommended_city
weather
events
reason

events는 문자열 배열이며 1~3개만 작성해주세요.
모든 내용은 한국어로 작성해주세요.
"""

    try:
        retry_response = client.models.generate_content(
            model="gemini-3.5-flash-lite",
            contents=retry_prompt
        )

        print("\n===== Gemini 재요청 응답 =====")
        print(retry_response.text)

        travel_data = json.loads(retry_response.text)

        required_keys = [
            "recommended_city",
            "weather",
            "events",
            "reason"
        ]

        for key in required_keys:
            if key not in travel_data:
                raise ValueError(f"필수 키 누락: {key}")

        if not isinstance(travel_data["recommended_city"], str):
            raise ValueError("recommended_city 타입 오류")

        if not isinstance(travel_data["weather"], str):
            raise ValueError("weather 타입 오류")

        if not isinstance(travel_data["events"], list):
            raise ValueError("events 타입 오류")

        if not isinstance(travel_data["reason"], str):
            raise ValueError("reason 타입 오류")

        print("\n===== JSON 재파싱 성공 =====")
        print(f"추천 도시: {travel_data['recommended_city']}")
        print(f"날씨: {travel_data['weather']}")
        print(f"행사: {travel_data['events']}")
        print(f"추천 이유: {travel_data['reason']}")

        return travel_data

    except Exception as e:

        print("\n===== JSON 재파싱 실패 =====")
        print(e)

        errors.append(f"Gemini JSON 파싱 실패: {str(e)}")
        return None


# ============================================================
# Kakao 맛집 검색
# ============================================================

def search_kakao_place(city, errors):

    url = "https://dapi.kakao.com/v2/local/search/keyword.json"

    query = f"{city} 맛집"

    params = urlencode({
        "query": query,
        "size": 5
    })

    request = Request(
        f"{url}?{params}",
        headers={
            "Authorization": f"KakaoAK {KAKAO_REST_API_KEY}"
        }
    )

    try:
        with urlopen(request) as response:
            data = json.loads(
                response.read().decode("utf-8")
            )

    except HTTPError as e:

        print("\n===== Kakao API 오류 =====")
        print(f"HTTP 오류: {e.code}")

        error_message = f"Kakao API HTTP 오류: {e.code}"

        try:
            error_body = e.read().decode("utf-8")
            print("Kakao 응답:")
            print(error_body)
            error_message += f" - {error_body}"
        except Exception:
            pass

        errors.append(error_message)

        print("맛집 데이터를 '데이터 없음'으로 처리하고 계속 진행합니다.")
        return []

    except URLError as e:

        print("\n===== Kakao 네트워크 오류 =====")
        print(e)

        errors.append(f"Kakao 네트워크 오류: {str(e)}")

        print("맛집 데이터를 '데이터 없음'으로 처리하고 계속 진행합니다.")
        return []

    except Exception as e:

        print("\n===== Kakao API 오류 =====")
        print(e)

        errors.append(f"Kakao API 오류: {str(e)}")

        print("맛집 데이터를 '데이터 없음'으로 처리하고 계속 진행합니다.")
        return []


    documents = data.get("documents", [])


    # 검색 결과가 없는 경우
    if not documents:

        print("\n===== Kakao 맛집 검색 결과 =====")
        print("데이터 없음")

        return []


    restaurants = []

    for place in documents:

        restaurant = {
            "name": place.get("place_name", ""),
            "address": (
                place.get("road_address_name")
                or place.get("address_name", "")
            ),
            "category": place.get("category_name", ""),
            "url": place.get("place_url", ""),
            "x": float(place["x"]) if place.get("x") else None,
            "y": float(place["y"]) if place.get("y") else None
        }

        restaurants.append(restaurant)


    print("\n===== Kakao 맛집 검색 결과 =====")

    for restaurant in restaurants:

        print(f"맛집: {restaurant['name']}")
        print(f"주소: {restaurant['address']}")
        print(f"카테고리: {restaurant['category']}")
        print(f"URL: {restaurant['url']}")
        print(
            f"좌표: x={restaurant['x']}, "
            f"y={restaurant['y']}"
        )
        print("-" * 40)


    return restaurants


# ============================================================
# 캐시 데이터 불러오기
# ============================================================

def load_cached_data(date):

    cache_file = Path("results") / f"travel_data_{date}.json"

    if not cache_file.exists():
        return None

    print("\n===== 캐시 데이터 발견 =====")
    print(f"기존 원본 데이터를 불러옵니다: {cache_file}")
    print("Gemini/Kakao API 호출을 건너뜁니다.")

    try:
        with open(cache_file, "r", encoding="utf-8") as f:
            cached_data = json.load(f)

        # 기존 저장 형식과 새 저장 형식을 모두 처리
        if "travel_data" not in cached_data:
            if "travel_recommendation" in cached_data:
                cached_data["travel_data"] = cached_data["travel_recommendation"]

        if "restaurants" not in cached_data:
            cached_data["restaurants"] = []

        return cached_data

    except Exception as e:

        print(f"캐시 데이터 읽기 오류: {e}")
        return None


# ============================================================
# API 호출 결과 캐시 저장
# ============================================================

def save_result_data(date, travel_data, restaurants, errors):

    os.makedirs("results", exist_ok=True)

    cache_file = Path("results") / f"travel_data_{date}.json"

    result_data = {
        "travel_data": travel_data,
        "restaurants": restaurants,
        "errors": errors
    }

    try:
        with open(
            cache_file,
            "w",
            encoding="utf-8"
        ) as file:

            json.dump(
                result_data,
                file,
                ensure_ascii=False,
                indent=2
            )

        print("\n===== API 결과 캐시 저장 완료 =====")
        print(f"캐시 데이터: {cache_file}")

    except Exception as e:

        print("\n===== 캐시 저장 오류 =====")
        print(e)

        errors.append(
            f"캐시 저장 오류: {str(e)}"
        )


# ============================================================
# 최종 여행 리포트 생성
# ============================================================

def generate_final_report(travel_data, restaurants, errors):

    prompt = f"""
다음 여행 추천 정보를 바탕으로 최종 여행 리포트를 작성해주세요.

[1차 여행 추천 JSON]
{json.dumps(travel_data, ensure_ascii=False, indent=2)}

[맛집 목록]
{json.dumps(restaurants, ensure_ascii=False, indent=2)}

다음 조건을 반드시 지켜주세요.

1. Markdown 형식으로 작성하세요.
2. 추천 지역과 추천 이유를 요약하세요.
3. 날씨를 요약하세요.
4. 행사/축제 목록을 작성하세요.
5. 맛집 리스트를 작성하세요.
6. 맛집 목록이 비어 있으면 반드시 "데이터 없음"이라고 표시하세요.
7. 오전 / 오후 / 저녁으로 나누어 1일 여행 일정을 제안하세요.
8. 제공된 정보에 없는 구체적인 사실은 임의로 만들어내지 마세요.

다음 형식으로 작성해주세요.

# 국내 여행 추천 리포트

## 1. 추천 지역
- 추천 지역:
- 추천 이유:

## 2. 날씨
-

## 3. 행사/축제
-

## 4. 맛집
- 맛집명:
  - 주소:
  - 카테고리:
  - URL:

## 5. 1일 여행 일정
### 오전
-

### 오후
-

### 저녁
-
"""

    try:

        response = client.models.generate_content(
            model="gemini-3.5-flash-lite",
            contents=prompt
        )

        print("\n===== 최종 여행 리포트 =====")
        print(response.text)

        return response.text

    except Exception as e:

        print("\n===== 최종 리포트 생성 오류 =====")
        print(e)

        errors.append(
            f"최종 리포트 생성 오류: {str(e)}"
        )

        fallback_report = f"""# 국내 여행 추천 리포트

## 1. 추천 지역
- 추천 지역: {travel_data.get("recommended_city", "데이터 없음")}
- 추천 이유: {travel_data.get("reason", "데이터 없음")}

## 2. 날씨
- {travel_data.get("weather", "데이터 없음")}

## 3. 행사/축제
"""

        events = travel_data.get("events", [])

        if events:
            for event in events:
                fallback_report += f"- {event}\n"
        else:
            fallback_report += "- 데이터 없음\n"

        fallback_report += "\n## 4. 맛집\n"

        if restaurants:
            for restaurant in restaurants:
                fallback_report += (
                    f"- 맛집명: {restaurant.get('name', '')}\n"
                    f"  - 주소: {restaurant.get('address', '')}\n"
                    f"  - 카테고리: {restaurant.get('category', '')}\n"
                    f"  - URL: {restaurant.get('url', '')}\n"
                )
        else:
            fallback_report += "- 데이터 없음\n"

        fallback_report += """
## 5. 1일 여행 일정

### 오전
- 추천 지역의 주요 관광 및 문화 활동

### 오후
- 지역 관광 및 식사

### 저녁
- 지역 맛집에서 식사하며 하루 마무리
"""

        return fallback_report


# ============================================================
# 결과 저장
# ============================================================

def save_results(date, travel_data, restaurants, errors, report):

    os.makedirs("results", exist_ok=True)

    json_path = os.path.join(
        "results",
        f"travel_data_{date}.json"
    )

    report_path = os.path.join(
        "results",
        f"travel_report_{date}.md"
    )


    # 최종 결과 데이터 저장
    result_data = {
        "travel_data": travel_data,
        "restaurants": restaurants,
        "errors": errors
    }

    with open(
        json_path,
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            result_data,
            file,
            ensure_ascii=False,
            indent=2
        )


    # 최종 여행 리포트 저장
    with open(
        report_path,
        "w",
        encoding="utf-8"
    ) as file:

        file.write(report)


    print("\n===== 결과 저장 완료 =====")
    print(f"원본 데이터: {json_path}")
    print(f"최종 리포트: {report_path}")


# ============================================================
# 메인 프로그램
# ============================================================

def main():

    parser = argparse.ArgumentParser(
        description="국내 여행 추천 프로그램"
    )

    parser.add_argument(
        "-date",
        "--date",
        required=True,
        help="여행 날짜를 YYYY-MM-DD 형식으로 입력하세요."
    )

    args = parser.parse_args()


    # 날짜 형식 확인
    try:

        datetime.strptime(
            args.date,
            "%Y-%m-%d"
        )

    except ValueError:

        parser.print_usage()

        print(
            "오류: 날짜는 YYYY-MM-DD 형식으로 입력해야 합니다."
        )

        return


    print(f"여행 날짜: {args.date}")


    # 오류 목록
    errors = []


    # ========================================================
    # 캐시 확인
    # ========================================================

    cached_data = load_cached_data(args.date)

    if cached_data:

        travel_data = cached_data["travel_data"]
        restaurants = cached_data["restaurants"]

        print(
            f"\n캐시에서 불러온 추천 도시: "
            f"{travel_data['recommended_city']}"
        )

    else:

        # ----------------------------------------------------
        # 1단계: Gemini 여행 추천
        # ----------------------------------------------------

        travel_data = get_travel_recommendation(
            args.date,
            errors
        )

        if travel_data is None:

            print("\n여행 추천 데이터를 생성하지 못했습니다.")

            if errors:
                print("\n===== 오류 목록 =====")

                for error in errors:
                    print(f"- {error}")

            return


        print(
            f"\n다음 단계로 전달할 도시: "
            f"{travel_data['recommended_city']}"
        )


        # ----------------------------------------------------
        # 2단계: Kakao 맛집 검색
        # ----------------------------------------------------

        restaurants = search_kakao_place(
            travel_data["recommended_city"],
            errors
        )


        # API 호출 결과 캐시 저장
        save_result_data(
            args.date,
            travel_data,
            restaurants,
            errors
        )


    # --------------------------------------------------------
    # 3단계: 최종 리포트 생성
    # --------------------------------------------------------

    report = generate_final_report(
        travel_data,
        restaurants,
        errors
    )


    # --------------------------------------------------------
    # 4단계: 결과 저장
    # --------------------------------------------------------

    save_results(
        args.date,
        travel_data,
        restaurants,
        errors,
        report
    )


    # 오류가 있었는지 표시
    if errors:

        print("\n===== 오류 요약 =====")

        for error in errors:
            print(f"- {error}")

    else:

        print("\n===== 오류 없음 =====")


# ============================================================
# 프로그램 실행
# ============================================================

if __name__ == "__main__":
    main()