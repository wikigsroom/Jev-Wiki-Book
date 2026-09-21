from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

assets = Path(__file__).resolve().parents[1] / "assets"
assets.mkdir(parents=True, exist_ok=True)
image = Image.new("RGBA", (256, 256))
draw = ImageDraw.Draw(image)
draw.rounded_rectangle((8, 8, 248, 248), radius=54, fill="#355bf5")
for box, color in [((57, 125, 88, 194), "#ffffff"), ((113, 62, 144, 194), "#ffffff"), ((169, 95, 200, 194), "#a8baff")]:
    draw.rounded_rectangle(box, radius=8, fill=color)
image.save(assets / "icon.png")
image.save(assets / "icon.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
splash = Image.new("RGB", (460, 240), "#f5f7fa")
splash.paste(image.resize((64, 64)), (38, 48), image.resize((64, 64)))
draw = ImageDraw.Draw(splash)
font = ImageFont.truetype("C:/Windows/Fonts/msyh.ttc", 18)
title = ImageFont.truetype("C:/Windows/Fonts/bahnschrift.ttf", 34)
draw.text((120, 53), "JEV", font=title, fill="#182b46")
draw.text((38, 142), "正在展开桌面运行环境…", font=font, fill="#576b86")
draw.text((38, 178), "完成后将自动打开本地文档工作台", font=font, fill="#576b86")
splash.save(assets / "splash.bmp")
print("Generated desktop icon and extraction splash")
