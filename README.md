# バトルルール画像をAmazon PhotosにアップロードするLambda関数


## 前提
1. AWSにアカウントがあり、AWS CLIの設定が済んでいること
2. Amazon Prime会員であること
3. Dockerがインストールされていて、Dockerコマンドが使えるようになっていること

## 1.セットアップ

### 1.1.フォントの設定
私は「イカモドキ(=Splatoon1)」を取得しています。  
**※2023/4/11現在は非公開らしいのでお好きなフォントを設定してください。**  
フォントは`.fonts`に入れてください。  
`app.py`のイカ項目でフォントファイルを指定してください。
```python
OUTPUT_DIR = "/tmp"

# スプラトゥーンのフォントを指定する
font_file = os.path.join(FONT_FILE_DIR, "Splatoon1.ttf")

# WebDriverにChromeを指定する。
```

### 1.2.Dockerセットアップ
```bash
# 環境変数にAWSの情報を設定する
$ AWS_DEFAULT_REGION=<デフォルトリージョンを指定する>
$ AWS_ACCOUNT_ID=<アカウントIDをしてする>

# ECRにコンテナリポジトリを作成する
aws ecr create-repository \
--repository-name upload-ikaring3-data-to-amazon-photos \
--image-scanning-configuration scanOnPush=true \
--region $AWS_DEFAULT_REGION

# ECRにログインする
aws ecr get-login-password --region $AWS_DEFAULT_REGION | docker login --username AWS --password-stdin ${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_DEFAULT_REGION}.amazonaws.com
```

## 2.開発
### 2.1.環境変数の設定
`.env.sample`の名前を変更し`.env`にしてください  
`.env`を編集して情報を入力する
```bash
# AMAZON ACCOUNT
AMAZON_ACCOUNT_EMAIL=<アマゾンアカウントのEメールアドレス>
AMAZON_ACCOUNT_PASS=<アマゾンアカウントのパスワード>

# AWS
AWS_DEFAULT_REGION=<AWSのデフォルトリージョン>
AWS_ACCESS_KEY_ID=<AWSのACCESS_KEY_ID>
AWS_SECRET_ACCESS_KEY=<AWSのシークレットアクセスキー>
```

### 2.2.コンテナの立ち上げ
```bash
#ローカルのDockerでコンテナ立ち上げ
$ docker compose up -d

#コンテナへのリクエスト
$ curl -XPOST "http://localhost:9001/2015-03-31/functions/function/invocations" -d '{}' 

#コンテナの削除
$ docker-compose down --rmi all --volumes --remove-orphans
```


## 3.AWS ECRへのデプロイ
```bash
#コンテナイメージの作成
$ docker build -t upload-ikaring3-data-to-amazon-photos .

#コンテナイメージタグの設定
$ docker tag upload-ikaring3-data-to-amazon-photos:latest ${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_DEFAULT_REGION}.amazonaws.com/upload-ikaring3-data-to-amazon-photos:latest

# ECRへのデプロイ
$ docker push ${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_DEFAULT_REGION}.amazonaws.com/upload-ikaring3-data-to-amazon-photos:latest

# コンテナイメージの削除
$ docker rmi ${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_DEFAULT_REGION}.amazonaws.com/upload-ikaring3-data-to-amazon-photos
$ docker rmi upload-ikaring3-data-to-amazon-photos
```

## 99.その他
```bash
# ECRのイメージが403でPullできない時は一度ログアウト
$ docker logout public.ecr.aws
```