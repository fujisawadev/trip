import boto3
import uuid
import os
from flask import current_app
from botocore.exceptions import ClientError
import logging
from werkzeug.utils import secure_filename

def get_s3_client():
    """S3クライアントを取得する"""
    return boto3.client(
        's3',
        aws_access_key_id=current_app.config['AWS_ACCESS_KEY_ID'],
        aws_secret_access_key=current_app.config['AWS_SECRET_ACCESS_KEY'],
        region_name=current_app.config['AWS_S3_REGION']
    )

def upload_file_to_s3(file, filename=None, content_type=None, acl=None, folder='spot_photo'):
    """ファイルをS3にアップロードする
    
    Args:
        file: アップロードするファイルオブジェクト
        filename: 保存するファイル名（指定しない場合はUUIDを生成）
        content_type: ファイルのMIMEタイプ（指定しない場合はファイルから推測）
        acl: アクセス権限（デフォルトはNone。バケットのデフォルト設定を使用）
        folder: 保存先フォルダ（デフォルトは'spot_photo'）
        
    Returns:
        成功した場合はS3のURL、失敗した場合はNone
    """
    # S3が有効かチェック
    if not current_app.config.get('USE_S3', False):
        return None
        
    # ファイル名が指定されていない場合は、安全なUUIDベースのファイル名を生成
    if filename is None:
        original_filename = secure_filename(file.filename)
        ext = os.path.splitext(original_filename)[1].lower() if '.' in original_filename else ""
        filename = f"{uuid.uuid4().hex}{ext}"
    
    # フォルダを付加してキーを生成（末尾にスラッシュがある場合とない場合を考慮）
    if folder:
        folder = folder.rstrip('/')
        key = f"{folder}/{filename}"
    else:
        key = filename
    
    # コンテンツタイプが指定されていない場合、ファイルから判断
    if content_type is None and hasattr(file, 'content_type'):
        content_type = file.content_type
    
    # S3クライアントを取得
    s3_client = get_s3_client()
    bucket_name = current_app.config['AWS_S3_BUCKET_NAME']
    
    try:
        # ExtraArgsの設定
        extra_args = {}
        
        # コンテンツタイプが指定されている場合は追加
        if content_type:
            extra_args["ContentType"] = content_type
            
        # ACLが指定されている場合のみACLを設定（現在はデフォルトではACLを使用しない）
        if acl:
            extra_args["ACL"] = acl
            
        # S3にアップロード
        s3_client.upload_fileobj(
            file,
            bucket_name,
            key,
            ExtraArgs=extra_args
        )
        
        # URLを生成して返す
        return f"https://{bucket_name}.s3.{current_app.config['AWS_S3_REGION']}.amazonaws.com/{key}"
    
    except ClientError as e:
        logging.error(f"S3アップロードエラー: {e}")
        return None
    except Exception as e:
        logging.error(f"予期しないエラー: {e}")
        return None

def delete_file_from_s3(file_url):
    """S3からファイルを削除する
    
    Args:
        file_url: 削除するファイルのURL
        
    Returns:
        成功した場合はTrue、失敗した場合はFalse
    """
    # S3が有効かチェック
    if not current_app.config.get('USE_S3', False):
        return False
        
    try:
        bucket_name = current_app.config['AWS_S3_BUCKET_NAME']
        s3_region = current_app.config['AWS_S3_REGION']
        
        # URLからファイル名（キー）を抽出
        base_url = f"https://{bucket_name}.s3.{s3_region}.amazonaws.com/"
        if file_url.startswith(base_url):
            key = file_url[len(base_url):]
            
            # S3クライアントを取得
            s3_client = get_s3_client()
            
            # オブジェクトを削除
            s3_client.delete_object(
                Bucket=bucket_name,
                Key=key
            )
            return True
        else:
            logging.warning(f"URLのフォーマットが期待通りではありません: {file_url}")
            return False
    except Exception as e:
        logging.error(f"S3削除エラー: {e}")
        return False 