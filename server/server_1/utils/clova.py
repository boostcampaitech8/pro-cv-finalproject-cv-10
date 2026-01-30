
import requests
import json
import os
import base64
import mimetypes


# export CLOVA_API_KEY = ""

HOST = 'https://clovastudio.stream.ntruss.com'
API_KEY = os.getenv('CLOVA_API_KEY', "")
REQUEST_ID = '450573ae85b94325a5b2720e77eaa790'

SYSTEM_MESSAGE = {
    "role": "system",
    "content": [
        {
            "type": "text",
            "text": "간결하고 객관적으로 답변하는 AI 어시스턴트입니다."
        }
    ]
}

def image_to_data_uri(image_path):
    mime_type, _ = mimetypes.guess_type(image_path)
    with open(image_path, 'rb') as img_file:
        img_bytes = img_file.read()

    encoded_bytes = base64.b64encode(img_bytes)
    encoded_string = encoded_bytes.decode('utf-8')

    data_uri = f"data:{mime_type};base64,{encoded_string}"
    return data_uri

class CompletionExecutor:
    def __init__(self, host=HOST, api_key=API_KEY, request_id=REQUEST_ID):
        self._host = host
        self._api_key = "Bearer " + api_key
        self._request_id = request_id

    def image_caption(self,image_path, json_path, text = "이 이미지에 대한 정보를 날씨에 대한 한 문장, 그리고 다음의 정보를 통해 한 문장으로 요약해 줘.") -> requests.Response:
        headers = {
            'Authorization': self._api_key,
            'X-NCP-CLOVASTUDIO-REQUEST-ID': self._request_id,
            'Content-Type': 'application/json; charset=utf-8',
        }
        data_uri = image_to_data_uri(image_path)
        with open(json_path, 'r', encoding='utf-8') as json_file:
            additional_info = json.load(json_file)
        text += f"\n객체 탐지 결과: {json.dumps(additional_info, ensure_ascii=False)}"

        completion_request = {
            "messages":[
                SYSTEM_MESSAGE,
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "imageUrl": None,
                            "dataUri": {
                                "data": data_uri
                            }
                        },
                        {
                            "type": "text",
                            "text": text
                        }
                    ]
                }
            ],
            "top_p":0.8,
            "topK":0,
            "maxTokens": 100,
            "temperature":0.5,
            "repititionPenalty":1.1,
            "stop":[]
        }

        response = requests.post(self._host + '/v3/chat-completions/HCX-005',
                                headers=headers,
                                json=completion_request,
                                stream=True)
        print(response.text)
        return json.loads(response.text)["result"]["message"]["content"]

    def report(self,text) -> requests.Response:
        headers = {
            'Authorization': self._api_key,
            'X-NCP-CLOVASTUDIO-REQUEST-ID': self._request_id,
            'Content-Type': 'application/json; charset=utf-8',
        }
        data ={
                "messages": [
                {
                    "role": "system",
                    "content": "- 미리 정의한 JSON Schema 형식에 맞춰 답변하는 AI 어시스턴트입니다."
                },
                {
                    "role": "user",
                    "content": text
                },
                ],
                "topP": 0.8,
                "topK": 0,
                "maxCompletionTokens": 100,
                "temperature": 0.5,
                "repetitionPenalty": 1.1,
                "thinking": {"effort": "none"},
                "stop": [],
                "responseFormat": {
                "type" : "json",
                "schema": {
                    "type": "object",
                    "properties": {
                        "weather": {
                            "type": "object",
                            "description": "날씨 정보"
                        },
                        "detected_object": {
                            "type": "object",
                            "description": "감지된 객체에 대한 정보"
                        },
                    },
                    "required": [
                    "weather",
                    "detected_object",
                    ]
                }
                }
            }
        response = requests.post(self._host + '/v3/api-tools/chat-tokenize/HCX-007',
                                headers=headers,
                                data= json.dumps(data),
                                stream=True)
        return json.loads(response.text)

if __name__ == '__main__':
    completion_executor = CompletionExecutor(
        host=HOST,
        api_key=API_KEY,
        request_id=REQUEST_ID
    )
    caption = completion_executor.image_caption(
        image_path='./frame_00.jpg',
        json_path='./frame_00.json')
    print(caption)

    report = completion_executor.report("이 이미지에 대한 정보를 요약해줘.")
    print(report["result"]["message"]["content"])
