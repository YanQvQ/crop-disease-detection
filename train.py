# ============================================
# 农作物病害识别系统 - 模型训练脚本
# @Author : 张炎 (YanQvQ)
# @GitHub : https://github.com/YanQvQ
# @Time   : 2026-03-12
# @File   : train.py
# ============================================
from ultralytics import YOLO
import warnings
warnings.filterwarnings('ignore')


if __name__ == '__main__':
    # 初始化模型
    model = YOLO("yolov8n.yaml", task="detect").load("yolov8n.pt")  # 从本地 YAML 构建并加载权重

    # 开始训练
    #results = model.train(data="./dataset/corn_dataset/data.yaml",
    results = model.train(data="./dataset/rice_dataset/data.yaml",
    #results = model.train(data="./dataset/wheat_dataset/data.yaml",
                          epochs=300,  #（int）训练的周期数
                          batch=-1,  # （int）每批次的图像数量（-1为自动批处理）
                          amp=False,  # 禁用AMP以避免加载yolo11n.pt错误
                          imgsz=640)
