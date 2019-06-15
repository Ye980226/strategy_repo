import talib as ta
import numpy as np
import pandas as pd

"""
将kdj策略需要用到的信号生成器抽离出来
"""

class DiverGenceGet():

    def __init__(self):
        self.author = 'zong'
    

    #### 计算direction index指标
    def DIget(self,barArray, paraDict):

        fastPeriod = paraDict['fastPeriod']
        slowPeriod = paraDict['slowPeriod']
        DIshield = paraDict['DIshield']
        DImaPeriod = paraDict['DImaPeriod']

        if len(barArray.close)<=slowPeriod+1:
            print('输入的bar数据长度不足，DI指标计算失败，请检查参数设置')
            return 0 
        
        ### 按照close价格计算每bar收益率
        pctChange = np.insert((barArray.close[1:]-barArray.close[:-1])/barArray.close[:-1],0,0)

        ### 计算最近的两个DI指标
        fastMom = ta.ROCP(barArray.close, fastPeriod) 
        slowMom = ta.ROCP(barArray.close, slowPeriod)

        slowSign = slowMom[-1]

        slowStd = ta.STDDEV(pctChange, slowPeriod)
        fastStd = ta.STDDEV(pctChange,fastPeriod)
        DI = (fastMom*slowMom)/(slowStd*fastStd)    

        DI_miu = ta.MA(DI, DImaPeriod)
        
        ######## 
        signal = 0  
        if DI[-1]<-DIshield and DI_miu[-1]-DI_miu[-2]>0:
            if slowSign>0: 
                signal = 1   # 1代表buy信号
            elif slowSign<0:
                signal = -1  # -1代表short信号

        return signal, DI, fastMom[-1]


    #### 计算ADX指标
    def ADXget(self,barArray,paraDict):

        ADXpara = paraDict['ADXpara']
        shield_up = paraDict['ADXshield_up']
        shield_down = paraDict['ADXshield_down']
        adx = ta.ADX(barArray.high,barArray.low,barArray.close,ADXpara)
        if adx[-1]<=shield_up and adx[-1]>=shield_down:
            signal = True
        else:
            signal = False
        
        return signal, adx[-1]








        



