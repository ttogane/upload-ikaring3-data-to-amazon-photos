import os
import os.path
import io
import time
import json
import boto3
import requests
import shutil
from datetime import datetime
from boto3.dynamodb.conditions import Attr
from PIL import Image, ImageFont, ImageDraw
from selenium import webdriver
from selenium.webdriver.support.wait import WebDriverWait
from selenium.webdriver.common.by import By
from enum import Enum


AMAZON_PHOTOS_ALBUM_TITLE = "Splatoon-3-schedules"
BATTLE_SCHEDULE_TABLE = "splatoon3-battle-schedules"
S3_DATA_BUCKET = "splatoon3-data"
CHROMEDRIVER = "/opt/chrome/chromedriver"

ASSETS_DIR = "./data/assets"
FONT_FILE_DIR = ".fonts"
OUTPUT_DIR = "/tmp"

# スプラトゥーンのフォントを指定する
font_file = os.path.join(FONT_FILE_DIR, "Splatoon1.ttf")

# WebDriverにChromeを指定する。
chrome_options = webdriver.ChromeOptions()
chrome_options.binary_location = "/opt/chrome/chrome"
chrome_options.add_argument('--headless')
chrome_options.add_argument('--no-sandbox')
chrome_options.add_argument("--disable-gpu")
chrome_options.add_argument("--single-process")
chrome_options.add_argument("--disable-dev-shm-usage")
chrome_options.add_argument("--disable-dev-tools")


class BattleType(Enum):
  REGULAR = "レギュラーマッチ"
  CHALLENGE = "バンカラマッチ(チャレンジ)"
  OPEN = "バンカラマッチ(オープン)"
  X = "Xマッチ"
  FEST = "フェスマッチ"

class ColorCode(Enum):
  YELLOW = "#D3F620"
  RED = "#E1562C"
  GREEN = "#64D79E"
  BLUE = "#4B39C0"
  WHITE = "#FFFFFF"
  BLACK = "#2D2D2D"


''' バトルスケジュールを取得する '''
def fetch_schedules():
  dynamodb = boto3.resource('dynamodb')
  table = dynamodb.Table(BATTLE_SCHEDULE_TABLE)

  timestamp = int(datetime.now().timestamp())
  response = table.scan(FilterExpression=Attr('start_time').lte(timestamp) & Attr('end_time').gt(timestamp))
  table_items = response['Items']
  return table_items


''' 二つの画像を水平につなげたimageを返却する '''
def get_concat_stage(stage1, stage2, margin = 0):

  image_width = stage1.width + stage2.width + margin
  image_height = stage1.height 
  img = Image.new('RGBA', (image_width, image_height))

  img.paste(stage1, (0, 0))
  img.paste(stage2, (stage1.width + margin, 0))
  return img


''' imageを丸角にして返却する
    rad = (left_top, left_bottom, right_top, right_bottom)
'''
def crop_corners(img, rad=(0, 0, 0, 0)):
  # left top corners
  circle_left_top = Image.new('L', (rad[0] * 2, rad[0] * 2), 0)
  draw_left_top = ImageDraw.Draw(circle_left_top)
  draw_left_top.ellipse((0, 0, rad[0] * 2, rad[0] * 2), fill=255)

  #left bottom corners
  circle_left_bottom = Image.new('L', (rad[1] * 2, rad[1] * 2), 0)
  draw_left_bottom = ImageDraw.Draw(circle_left_bottom)
  draw_left_bottom.ellipse((0, 0, rad[1] * 2, rad[1] * 2), fill=255)

  # right top corners
  circle_right_top = Image.new('L', (rad[2] * 2, rad[2] * 2), 0)
  draw_right_top = ImageDraw.Draw(circle_right_top)
  draw_right_top.ellipse((0, 0, rad[2] * 2, rad[2] * 2), fill=255)

  # right bottom corners
  circle_right_bottom = Image.new('L', (rad[3] * 2, rad[3] * 2), 0)
  draw_right_bottom = ImageDraw.Draw(circle_right_bottom)
  draw_right_bottom.ellipse((0, 0, rad[3] * 2, rad[3] * 2), fill=255)
  
  alpha = Image.new('L', img.size, 255)
  w, h = img.size
  alpha.paste(circle_left_top.crop((0, 0, rad[0], rad[0])), (0, 0)) 
  alpha.paste(circle_left_bottom.crop((0, rad[1], rad[1], rad[1] * 2)), (0, h - rad[1])) 
  alpha.paste(circle_right_top.crop((rad[2], 0, rad[2] * 2, rad[2])), (w - rad[2], 0)) 
  alpha.paste(circle_left_bottom.crop((rad[3], rad[3], rad[3] * 2, rad[3] * 2)), (w - rad[3], h - rad[3])) 
  img.putalpha(alpha)
  return img


''' 文字色を取得する '''
def get_text_color(battle_type):
  if battle_type == BattleType.CHALLENGE.value or battle_type == BattleType.OPEN.value:
    return ColorCode.RED.value
  elif battle_type == BattleType.X.value:
    return ColorCode.GREEN.value
  elif battle_type == BattleType.REGULAR.value:
    return ColorCode.YELLOW.value
  else:
    return ColorCode.WHITE.value


''' 文字だけのimageを作成し返却する '''
def get_text_image(text, color, size=10, algin = ""):
  font = ImageFont.truetype(font_file, size)
  (font_w, font_h), (offset_x, offset_y) = font.font.getsize(text)
  img = Image.new("RGBA", (font_w + offset_x, font_h + offset_y + int(font_h * 0.5))) # フォントの関係で文字の下部が見切れるため+5で調整
  img_w, img_h = img.size
  draw = ImageDraw.Draw(img)
  
  position = (offset_x, offset_y)
  if algin == "center":
    position = ((img_w - font_w) / 2, (img_h - font_h) / 2)
  elif algin == "vertical_center":
    position = (offset_x, (img_h - font_h) / 2)
  elif algin == "horizontal_center":
    position = ((img_w - font_w) / 2, offset_y)
  draw.text(position, text, color, font=font)

  return img

''' ステージ画像にステージ名を書き込み返却する '''
def get_stage_info_image(size: tuple, text, color, font_size=10):
  plate_size = (int(size[0] * 0.55), int(size[1] * 0.25))
  stage_info_img = Image.new('RGBA', plate_size, color=ColorCode.BLACK.value)
  stage_text = get_text_image(text, color, font_size, "vertical_center")
  stage_info_img.paste(stage_text, (5, 0), stage_text)
  stage_info_img = crop_corners(stage_info_img, (15, 0, 0, 0))

  return stage_info_img

''' マッチのアイコン画像を取得する '''
def get_battle_type_image(size: tuple, battle_type):
  battle_type_img: Image

  if battle_type == BattleType.CHALLENGE.value or battle_type == BattleType.OPEN.value:
    battle_type_img = Image.open(os.path.join(ASSETS_DIR, "BANCOLOR.png")).convert("RGBA")
  elif battle_type == BattleType.X.value:
    battle_type_img = Image.open(os.path.join(ASSETS_DIR, "X.png")).convert("RGBA")
  elif battle_type == BattleType.FEST.value:
    battle_type_img = Image.open(os.path.join(ASSETS_DIR, "FEST.png")).convert("RGBA")
  else:
    battle_type_img = Image.open(os.path.join(ASSETS_DIR, "TURF_WAR.png")).convert("RGBA")
  battle_type_img = battle_type_img.resize(size)

  return battle_type_img

''' ルールのアイコン画像を取得する '''
def get_rule_image(size: tuple, battle_rule):
  battle_rule_img: Image

  if battle_rule == "ガチアサリ":
    battle_rule_img = Image.open(os.path.join(ASSETS_DIR, "CLAM.png")).convert("RGBA")
  elif battle_rule == "ガチエリア":
    battle_rule_img = Image.open(os.path.join(ASSETS_DIR, "AREA.png")).convert("RGBA")
  elif battle_rule == "ガチホコバトル":
    battle_rule_img = Image.open(os.path.join(ASSETS_DIR, "GOAL.png")).convert("RGBA")
  elif battle_rule == "ガチヤグラ":
    battle_rule_img = Image.open(os.path.join(ASSETS_DIR, "LOFT.png")).convert("RGBA")
  elif battle_rule == "フェスマッチ" or battle_rule == "トリカラバトル":
    battle_rule_img = Image.open(os.path.join(ASSETS_DIR, "FEST.png")).convert("RGBA")
  else:
    battle_rule_img = Image.open(os.path.join(ASSETS_DIR, "TURF_WAR.png")).convert("RGBA")
  battle_rule_img = battle_rule_img.resize(size)
  
  return battle_rule_img


''' バトルのスケジュールイメージ画像を作成する。 '''
def create_battle_schedule_img(stage, battle_type, battle_rule, size = (860, 430), color = "#FFFFFF"):
  background = Image.new('RGBA', size, color=ColorCode.BLACK.value)
  text_color = get_text_color(battle_type)

  # Paste Stage
  stage_w, stage_h = stage.size
  stage_position = (int(size[0] / 2 - stage_w / 2), int(size[1] / 2))
  background.paste(stage, stage_position, stage)
  
  # Write Battle Type
  battle_type_img = get_battle_type_image((int(size[1] * 0.3), int(size[1] * 0.3)), battle_type)
  battle_type_text_img = get_text_image(battle_type, text_color, 44, "center")
  type_w, type_h = battle_type_img.size
  type_text_w, type_text_h = battle_type_text_img.size
  type_position = (int(size[0] / 2 - (type_w + type_text_w) / 2), 0)
  type_text_position = (type_position[0]  + type_w, type_position[1])

  background.paste(battle_type_img, type_position, battle_type_img)
  background.paste(battle_type_text_img, type_text_position, battle_type_text_img)
  
  # Write Battle Rule
  battle_rule_img = get_rule_image((int(size[1] * 0.2), int(size[1] * 0.2)), battle_rule)
  battle_rule_text_img = get_text_image(battle_rule, text_color, 36, "center")
  rule_w, rule_h = battle_rule_img.size
  rule_text_w, rule_text_h = battle_rule_text_img.size
  rule_position = (int(size[0] / 2 - (rule_w + rule_text_w) / 2), type_h)
  rule_text_position = (rule_position[0]  + rule_w, rule_position[1])

  background.paste(battle_rule_img, rule_position, battle_rule_img)
  background.paste(battle_rule_text_img, rule_text_position, battle_rule_text_img)

  return background


''' ルールごとの画像を生成し保存する。 '''
def create_images(schedules):
  print("create stages")
  regular_schedule = [schedule for schedule in schedules if schedule["battle_type"]  == BattleType.REGULAR.value]
  challenge_schedule = [schedule for schedule in schedules if schedule["battle_type"]  == BattleType.CHALLENGE.value]
  open_schedule = [schedule for schedule in schedules if schedule["battle_type"]  == BattleType.OPEN.value]
  x_schedule = [schedule for schedule in schedules if schedule["battle_type"]  == BattleType.X.value]
  fest_schedule = [schedule for schedule in schedules if schedule["battle_type"]  == BattleType.FEST.value and schedule["rule"] == BattleType.FEST.value]
  fest_tricolor_schedule = [schedule for schedule in schedules if schedule["battle_type"]  == BattleType.FEST.value and schedule["rule"] == "トリカラバトル"]
  
  all_schedule = [regular_schedule, challenge_schedule, open_schedule, x_schedule, fest_schedule, fest_tricolor_schedule]
  for schedule in all_schedule:
    if len(schedule) == 0:
        continue
    
    stage: Image
    battle_type = schedule[0]["battle_type"]
    rule = schedule[0]["rule"]
    text_color = ColorCode.WHITE.value
    if len(schedule) == 2:
      image_file = os.path.join(OUTPUT_DIR, battle_type + ".png")
      stage1 = Image.open(io.BytesIO(requests.get(schedule[0]["image"]).content))
      stage2 = Image.open(io.BytesIO(requests.get(schedule[1]["image"]).content))
      stage_info = get_stage_info_image(stage1.size, schedule[0]["stage"], text_color, 24)
      stage1.paste(stage_info, (stage1.width - stage_info.size[0], stage1.height - stage_info.size[1]), stage_info)
      stage_info = get_stage_info_image(stage2.size, schedule[1]["stage"], text_color, 24)
      stage2.paste(stage_info, (stage2.width - stage_info.size[0], stage2.height - stage_info.size[1]), stage_info)
      
      stage1 = crop_corners(stage1, (25, 25, 25, 25))
      stage2 = crop_corners(stage2, (25, 25, 25, 25))
      stage = get_concat_stage(stage1, stage2, 20)
    
    elif len(schedule) == 1:
      image_file = os.path.join(OUTPUT_DIR, rule + ".png")
      stage = Image.open(io.BytesIO(requests.get(schedule[0]["image"]).content))
      stage_info = get_stage_info_image(stage.size, schedule[0]["stage"], text_color, 24)
      stage.paste(stage_info, (stage.width - stage_info.size[0], stage.height - stage_info.size[1]), stage_info)
      stage = crop_corners(stage, (25, 25, 25, 25))
    
    create_battle_schedule_img(stage, battle_type, rule).save(image_file)


''' 対象のdir内の指定拡張子ファイル一覧を取得する '''
def list_img_data(dir):
  file_extention = (".img", ".png", ".jpg", ".jpeg")
  return [os.path.join(os.getcwd(), dir, file) for file in  filter(lambda file: file.endswith(file_extention) ,os.listdir(dir))]


''' 画像をAmazon Photosにアップロードする '''
def upload():
  print("upload to Amazon Photos")
  try:
    chrome_driver = webdriver.Chrome(options=chrome_options, executable_path="/opt/chromedriver")
    # Amazon photos ログインページにアクセスする
    chrome_driver.get(
      "https://www.amazon.co.jp/ap/signin?openid.pape.max_auth_age=3600&openid.return_to=https%3A%2F%2Fwww.amazon.co.jp%2Fphotos%3Fsf%3D1%2Fref_%3DAP_JP_HR_21_ULS&openid.identity=http%3A%2F%2Fspecs.openid.net%2Fauth%2F2.0%2Fidentifier_select&openid.assoc_handle=amzn_photos_web_jp&openid.mode=checkid_setup&language=ja_JP&openid.claimed_id=http%3A%2F%2Fspecs.openid.net%2Fauth%2F2.0%2Fidentifier_select&openid.ns=http%3A%2F%2Fspecs.openid.net%2Fauth%2F2.0"
    )
    # Seleniumがロードのために少なくとも10秒待機するように設定
    chrome_driver.implicitly_wait(10)
    
    # アマゾンの認証情報を入力する
    print("Amazon Photos Login")
    name_field = chrome_driver.find_element(By.ID, "ap_email")
    password_field = chrome_driver.find_element(By.ID, "ap_password")
    name_field.clear()
    name_field.send_keys(os.getenv("AMAZON_ACCOUNT_EMAIL"))
    password_field.clear()
    password_field.send_keys(os.getenv("AMAZON_ACCOUNT_PASS"))
    chrome_driver.find_element(By.ID, "signInSubmit").click()
    time.sleep(30) # Amazonがアカウント保護のためSMSで承認メッセージを飛ばすことがあるので対策(=30秒以内にSMSで反応できれば回避できる)

    # アルバムを開く
    print("Open album and remove old images")
    chrome_driver.find_element(By.CLASS_NAME, "albums").click()
    albums = chrome_driver.find_elements(By.CLASS_NAME, "thumbnail-selection-link")
    album_containers = chrome_driver.find_elements(By.CLASS_NAME, "album-container")

    target_album_index = 0
    for container in album_containers:
      album_title = container.find_element(By.CLASS_NAME, "details").find_element(By.CLASS_NAME, "album-title").text
      if album_title == AMAZON_PHOTOS_ALBUM_TITLE:
        albums[target_album_index].click()
        break

      target_album_index += 1
    # 前のスケジュール画像を全選択し削除を実行
    if len(chrome_driver.find_elements(By.CLASS_NAME, "count-select")) > 0:
      chrome_driver.find_element(By.CLASS_NAME, "count-select").click()
      wait = WebDriverWait(chrome_driver, 30);
      chrome_driver.find_element(By.CSS_SELECTOR, ".selection-header .selection-options .expandable-nav").click()
      chrome_driver.find_element(By.CSS_SELECTOR, ".selection-action.list.trash").click()
      chrome_driver.find_element(By.CSS_SELECTOR, ".dialog footer button+button").click()
      time.sleep(10) # モーダルが開き切るまで待機する(implicitly_waitではないため)

    # 今のスケジュール画像をアルバムにアップロードする。
    print("Upload new images")
    files = list_img_data(OUTPUT_DIR)
    chrome_driver.find_element(By.CLASS_NAME, "uploader-file-selector").send_keys("\n".join(files))
    time.sleep(10) # モーダルが開き切るまで待機する(implicitly_waitではないため)
    chrome_driver.find_element(By.CLASS_NAME, "uploader-status-completed-add-to-album").click()
    albums = chrome_driver.find_elements(By.CLASS_NAME, "album-select")

    target_album_index = 0
    for album in albums:
      album_title = album.find_element(By.CLASS_NAME, "details").find_element(By.CLASS_NAME, "album-title").text
      if album_title == AMAZON_PHOTOS_ALBUM_TITLE:
        albums[target_album_index].click()
        break
      target_album_index += 1
    time.sleep(10) # モーダルが開き切るまで待機する(implicitly_waitではないため)
    
    chrome_driver.close()

  except Exception as e: 
    print(e)


def handler(event, context):

  # バトルスケジュールを取得
  schedules = fetch_schedules()

  # バトルスケジュールの画像を作成
  create_images(schedules)
  
  # Amazon Photosにアップロード
  upload()
  
  return json.dumps({"message": "OK"})