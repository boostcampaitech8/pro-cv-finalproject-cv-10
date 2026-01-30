import asyncio
import base64
import json
import mimetypes
import time
from dataclasses import dataclass
from pathlib import Path
import os
import httpx  

HOST = 'https://clovastudio.stream.ntruss.com'
API_KEY = os.getenv('CLOVA_API_KEY', "")
REQUEST_ID = '450573ae85b94325a5b2720e77eaa790'

SYSTEM_MESSAGE = {
    "role": "system",
    "content": [{"type": "text", "text": "간결하고 객관적으로 답변하는 AI 어시스턴트입니다."}],
}

# 위 함수 변수명 버그 수정 버전
def image_to_data_uri(image_path: str) -> str:
    mime_type, _ = mimetypes.guess_type(image_path)
    with open(image_path, "rb") as f:
        img_bytes = f.read()
    encoded_string = base64.b64encode(img_bytes).decode("utf-8")
    return f"data:{mime_type};base64,{encoded_string}"

@dataclass
class CompletionExecutorAsync:
    host: str
    api_key: str
    request_id: str
    model_path: str = "/v3/chat-completions/HCX-005"

    def _headers(self) -> dict:
        return {
            "Authorization": "Bearer " + self.api_key,
            "X-NCP-CLOVASTUDIO-REQUEST-ID": self.request_id,
            "Content-Type": "application/json; charset=utf-8",
        }

    async def execute_one(self, client: httpx.AsyncClient, image_path: str, json_path: str, text: str) -> str:
        t0 = time.perf_counter()

        data_uri = image_to_data_uri(image_path)
        with open(json_path, "r", encoding="utf-8") as f:
            additional_info = json.load(f)

        text2 = text + f"\n객체 탐지 결과: {json.dumps(additional_info, ensure_ascii=False)}"

        payload = {
            "messages": [
                SYSTEM_MESSAGE,
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "imageUrl": None,
                            "dataUri": {"data": data_uri},
                        },
                        {"type": "text", "text": text2},
                    ],
                },
            ],
            "top_p": 0.8,
            "topK": 0,
            "maxTokens": 100,
            "temperature": 0.5,
            "repititionPenalty": 1.1,
            "stop": [],
            "stream": False,  # 지금 코드는 스트리밍 파싱 안 하므로 False 권장
        }

        resp = await client.post(self.host + self.model_path, headers=self._headers(), json=payload)
        resp.raise_for_status()

        data = resp.json()
        caption = data["result"]["message"]["content"]

        dt = time.perf_counter() - t0
        return f"[{Path(image_path).name}] {dt:.3f}s | {caption}"

async def main():
    print(API_KEY)
    executor = CompletionExecutorAsync(host=HOST, api_key=API_KEY, request_id=REQUEST_ID)

    prompt = "이 이미지에 대한 정보를 날씨에 대한 한 문장, 그리고 다음의 정보를 통해 한 문장으로 요약해 줘."

    # 예시: 같은 파일로 5번 요청(테스트용). 실제로는 리스트에 다른 경로를 넣으면 됨.
    jobs = [
        ("./frame_00.jpg", "./frame_00.json"),
        ("./frame_00.jpg", "./frame_00.json"),
        ("./frame_00.jpg", "./frame_00.json"),
        ("./frame_00.jpg", "./frame_00.json"),
        ("./frame_00.jpg", "./frame_00.json"),
    ]

    t_all = time.perf_counter()
    async with httpx.AsyncClient(timeout=httpx.Timeout(60.0)) as client:
        tasks = [
            executor.execute_one(client, image_path=img, json_path=js, text=prompt)
            for (img, js) in jobs
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)  # 동시 실행 [web:92]
    total = time.perf_counter() - t_all

    for r in results:
        if isinstance(r, Exception):
            print("ERROR:", repr(r))
        else:
            print(r)

    print(f"TOTAL: {total:.3f}s for {len(jobs)} requests")

if __name__ == "__main__":
    asyncio.run(main())
