
from pymongo.mongo_client import MongoClient
from pymongo.server_api import ServerApi
from pymongo.errors import DuplicateKeyError, PyMongoError
from datetime import datetime
from typing import List, Dict, Optional
import os
from dotenv import load_dotenv
from bson.objectid import ObjectId

load_dotenv()

class MongoDBAtlasManager:
    # MongoDB Atlas에 연결
    def __init__(self, uri: str = "", db_name: str = "data_metadata", collection_name: str = "files"):
        
        self.client = MongoClient(uri, server_api=ServerApi('1'))
        
        #연결 확인.
        try:
            self.client.admin.command('ping')
        except Exception as e:
            raise ConnectionError(f"MongoDB 연결 실패: {e}")
        
        self.db = self.client[db_name] # "data_metadata"
        self.collection = self.db[collection_name] # "files"
        self._create_indexes()
    
    def _create_indexes(self):
        #인덱스 생성
        self.collection.create_index([("created_at", -1)])
        self.collection.create_index([("location_name", -1)])
        self.collection.create_index([("remote_file_path", 1)], unique=True)
    
    # =================== CREATE ===================
    def create(self, 
               created_at: datetime,
               remote_file_path: str,
               location_name: str,
               metadata: Dict = None) -> str:

        # TODO: 이 구조 변경.
        doc = {
            "created_at": created_at,
            "remote_file_path": remote_file_path,
            "location_name": location_name,
            "metadata": metadata or {},
            "updated_at": datetime.utcnow()
        }

        result = self.collection.insert_one(doc)
        return str(result.inserted_id)
    
    # =================== READ ===================
    # 모든 파일
    def read_all(self, limit: int = 100) -> List[Dict]:
        return list(self.collection.find().sort("created_at", -1).limit(limit))
    
    # id로 조회
    def read_by_id(self, doc_id: str) -> Optional[Dict]:
        try:
            return self.collection.find_one({"_id": ObjectId(doc_id)})
        except Exception:
            return None
        
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
    
    # =================== DELETE ===================
    # 파일 메타데이터 삭제
    # ID로 삭제
    def delete_by_id(self, doc_id: str) -> int:
        result = self.collection.delete_one({"_id": ObjectId(doc_id)})
        return result.deleted_count
    
    # 경로로 삭제
    def delete_by_path(self, remote_file_path: str) -> int:
        result = self.collection.delete_one({"remote_file_path": remote_file_path})
        return result.deleted_count
    
    # 조건으로 삭제
    def delete_batch(self, query_dict: Dict) -> int:
        result = self.collection.delete_many(query_dict)
        return result.deleted_count
    
    def close(self):
        self.client.close()
