#!/usr/bin/env python3
import os
import sys
import io
from PIL import Image

# 親ディレクトリをパスに追加
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import create_app
from app.utils.s3_utils import upload_file_to_s3

def create_test_image():
    """テスト用の画像を作成"""
    # 100x100の赤い画像を作成
    image = Image.new('RGB', (100, 100), color='red')
    
    # 画像をバイトストリームに保存
    img_io = io.BytesIO()
    image.save(img_io, 'JPEG')
    img_io.seek(0)
    
    # FileStorageオブジェクトのようにふるまうクラス
    class MockFileStorage:
        def __init__(self, stream, filename, content_type):
            self.stream = stream
            self.filename = filename
            self.content_type = content_type
            
        def read(self, *args, **kwargs):
            return self.stream.read(*args, **kwargs)
    
    # モックオブジェクトを返す
    return MockFileStorage(
        stream=img_io,
        filename='test_image.jpg',
        content_type='image/jpeg'
    )

def test_s3_upload():
    """S3アップロードをテスト"""
    print("S3アップロードテストを開始します...")
    
    # Flaskアプリケーションを作成
    app = create_app()
    
    with app.app_context():
        # S3が有効かチェック
        if not app.config.get('USE_S3'):
            print("エラー: S3が有効になっていません")
            return False
            
        # S3認証情報が設定されているかチェック
        if not all([
            app.config.get('AWS_ACCESS_KEY_ID'),
            app.config.get('AWS_SECRET_ACCESS_KEY'),
            app.config.get('AWS_S3_BUCKET_NAME')
        ]):
            print("エラー: S3認証情報が不足しています")
            return False
            
        print(f"バケット名: {app.config.get('AWS_S3_BUCKET_NAME')}")
        print(f"リージョン: {app.config.get('AWS_S3_REGION')}")
        
        # テスト画像を作成
        test_file = create_test_image()
        
        # S3にアップロード (spot_photoフォルダに保存)
        try:
            s3_url = upload_file_to_s3(test_file, folder='spot_photo')
            
            if s3_url:
                print(f"アップロード成功: {s3_url}")
                
                # URLにspot_photoが含まれていることを確認
                if 'spot_photo/' in s3_url:
                    print("✓ 正しいフォルダにアップロードされました")
                else:
                    print("✗ 指定したフォルダにアップロードされていません")
                    return False
                    
                return True
            else:
                print("アップロード失敗: URLが返されませんでした")
                return False
                
        except Exception as e:
            print(f"エラー: {str(e)}")
            return False

if __name__ == "__main__":
    success = test_s3_upload()
    
    if success:
        print("\n✅ テスト成功: S3アップロードが正常に動作しています")
        sys.exit(0)
    else:
        print("\n❌ テスト失敗: S3アップロードに問題があります")
        sys.exit(1) 