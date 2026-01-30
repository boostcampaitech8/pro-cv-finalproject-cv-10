
from functools import wraps
import boto3
from pymongo.mongo_client import MongoClient
from pymongo.server_api import ServerApi
from pymongo.errors import DuplicateKeyError, PyMongoError
from datetime import datetime
from typing import Callable, List, Dict, Optional
import os
from dotenv import load_dotenv
from bson.objectid import ObjectId
from sklearn.conftest import wraps
from PIL import Image
from io import BytesIO

"""

export URI=

export AWS_ACCESS_KEY_ID=

export AWS_SECRET_ACCESS_KEY=

"""

URI = os.environ.get("URI")
AWS_ACCESS_KEY_ID = os.environ.get("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = os.environ.get("AWS_SECRET_ACCESS_KEY")
BUCKET = "pro-cv-finalproject-cv-10-ehekafhr"

load_dotenv()


class DBManager:
    # MongoDB Atlas에 연결
    def __init__(self, uri: str = URI, db_name: str = "test", collection_name: str = "files"):
        
        self.client = MongoClient(uri, server_api=ServerApi('1'))
        
        #연결 확인.
        try:
            self.client.admin.command('ping')
        except Exception as e:
            raise ConnectionError(f"MongoDB 연결 실패: {e}")
                
        self.db = self.client[db_name] # "data_metadata"
        self.collection = self.db[collection_name] # "files"
        self.client_status_collection = self.db["client_status"]  # 클라이언트 상태 저장 컬렉션
        self._create_indexes()
        
        self.s3 = boto3.client("s3", region_name="ap-southeast-2",
                        aws_access_key_id=AWS_ACCESS_KEY_ID,
                        aws_secret_access_key=AWS_SECRET_ACCESS_KEY)
        
        

    def _create_indexes(self):
        #인덱스 생성
        self.collection.create_index([("created_at", -1)])
        self.collection.create_index([("location_name", -1)])
        self.collection.create_index([("remote_file_path", 1)], unique=True)
        self.collection.create_index([("client_id", 1)])
        
        #클라이언트 상태.
        self.client_status_collection.create_index([("client_id", 1)], unique=True)
    
    # =================== CREATE ===================

    def create(self, 
               created_at: datetime,
               remote_file_path: str,
               location_name: str,
               client_id: str,
               metadata: Dict = None,
               caption: str = "",
               event: bool = False,
               current_file_path: str = None) -> str:

        # TODO: 이 구조 변경.
        doc = {
            "created_at": created_at,
            "remote_file_path": remote_file_path,
            "location_name": location_name,
            "client_id": client_id,
            "metadata": metadata or {},
            "updated_at": datetime.utcnow(),
            "caption": caption,
            "event": event
        }
        # S3
        result = self.collection.insert_one(doc)
        self.s3.upload_file(current_file_path, BUCKET, remote_file_path)

        
        return str(result.inserted_id)
  
    
    # =================== READ ===================
    # 모든 파일 메타데이터 조회
    def read_all(self, limit: int = 100) -> List[Dict]:
        return list(self.collection.find().sort("created_at", -1).limit(limit))
    
    # id로 조회
    def read_by_id(self, doc_id: str) -> Optional[Dict]:
        try:
            meta = self.collection.find_one({"_id": ObjectId(doc_id)})
        except Exception:
            return None
        return meta
        
    # 파일 경로(S3)로 조회
    def read_by_path(self, remote_file_path: str) -> Optional[Dict]:
        return self.collection.find_one({"remote_file_path": remote_file_path})
    
    # 시간(between)으로 조회.
    def read_by_time(self, start_date: datetime, end_date: datetime) -> List[Dict]:
        return list(self.collection.find({
            "created_at": {"$gte": start_date, "$lte": end_date}
        }).sort("created_at", -1))
    
    # 위치로 조회
    def read_by_location(self, location_name: str) -> List[Dict]:
        return list(self.collection.find({"location_name": location_name}))

    # 커스텀 쿼리 조회
    def read_by_query(self, query_dict: Dict) -> List[Dict]:
        return list(self.collection.find(query_dict))
    
    # 이미지 파일들 로드
    def load_images(self, meta_list: List[Dict]) -> List[Image.Image]:
        images = []
        for meta in meta_list:
            remote_path = meta["remote_file_path"]
            s3_object = self.s3.get_object(Bucket=BUCKET, Key=remote_path)
            img_data = s3_object['Body'].read()
            img = Image.open(BytesIO(img_data))
            images.append(img)
        return images
    
        # client id로 상태 조회
    def get_client_status(self, client_id: str) -> Dict:
        return self.client_status_collection.find_one({"client_id": client_id})

    # 모든 클라이언트 상태 조회
    def get_all_client_status(self) -> List[Dict]:
        return list(self.client_status_collection.find().sort("updated_at", -1))

    # =================== UPDATE ===================
    # 파일 메타데이터 수정
    # ID로 수정
    def update_by_id(self, doc_id: str, **kwargs) -> int:
        """
        Usage: 
        db.update_by_id(
            "s3://bucket/file.dat",
            metadata={}
        )
        """
        """ID로 수정"""
        update_data = {**kwargs, "updated_at": datetime.utcnow()}
        result = self.collection.update_one(
            {"_id": ObjectId(doc_id)},
            {"$set": update_data}
        )
        return result.modified_count
    
    def update_by_path(self, remote_file_path: str, **kwargs) -> int:
        update_data = {**kwargs, "updated_at": datetime.utcnow()}
        result = self.collection.update_one(
            {"remote_file_path": remote_file_path},
            {"$set": update_data}
        )
        return result.modified_count
        # client id를 받아서 상태 저장
        
    def set_client_status(self, client_id: str, status: bool) -> bool:
        self.client_status_collection.update_one(
            {"client_id": client_id},
            {
                "$set": {
                    "client_id": client_id,
                    "status": status,
                    "updated_at": datetime.utcnow()
                }
            },
            upsert=True  # 없으면 생성, 있으면 업데이트
        )
        return True

    # =================== DELETE ===================
    
    # 경로로 삭제
    def delete_by_path(self, remote_file_path: str) -> int:
        result = self.collection.delete_one({"remote_file_path": remote_file_path})

        try:
            self.s3.delete_object(Bucket=BUCKET, remote_file_path=remote_file_path)
        except Exception as e:
            print(f"S3 delete failed for {remote_file_path}: {e}")
            raise
        
        return result.deleted_count
    
    # 조건으로 삭제
    def delete_batch(self, query_dict: Dict) -> int:
        metas = self.collection.find(query_dict)
        for meta in metas:
            try:
                self.s3.delete_object(Bucket=BUCKET, Key=meta["remote_file_path"])
            except Exception as e:
                print(f"S3 delete failed for {meta['remote_file_path']}: {e}")
                raise
        result = self.collection.delete_many(query_dict)
        return result.deleted_count




    # client id로 상태 삭제
    def delete_client_status(self, client_id: str) -> int:
        result = self.client_status_collection.delete_one({"client_id": client_id})
        return result.deleted_count
    
    # count documents. "files"에 저장.
    def count_documents(self, collection_name: str = "files", query_dict: Dict = None) -> int:
        collection = self.db[collection_name]
        if query_dict is None:
            return collection.count_documents({})
        else:
            return collection.count_documents(query_dict)

    
    def close(self):
        self.client.close()
    