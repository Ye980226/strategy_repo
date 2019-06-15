import talib as ta
import numpy as np
import pandas as pd

"""
将kdj策略需要用到的信号生成器抽离出来
"""

class DiverGenceGet():

    def __init__(self):
        self.author = 'zong'

    ### 计算macd背离
    def MACDget(self,barArray, paraDict):
        
        fastPeriod = paraDict['fastPeriod']  # 计算macd指标的参数
        fastMaType = paraDict['fastMaType']  # 计算macd指标的参数
        slowPeriod = paraDict['slowPeriod']  # 计算macd指标的参数
        slowMaType = paraDict['slowMaType']  # 计算macd指标的参数
        signalPeriod = paraDict['signalPeriod']  # 计算macd指标的参数
        signalMaType = paraDict['signalMaType']  # 计算macd指标的参数
        lagPeriod = paraDict['lagPeriod']  # 发生交叉的点向后寻找k线的根数
        maxPeriod = paraDict['maxPeriod']  # 两个交叉点距离的最小值
        minPeriod = paraDict['minPeriod']  # 两个交叉点距离的最大点

        macd, macdSignal, _ = ta.MACDEXT(barArray.close, fastPeriod, fastMaType, \
                        slowPeriod, slowMaType, signalPeriod, signalMaType)
        
        ### 对macd和macdSignal的空值进行处理以防止后面比较大小时出错
        macd[np.isnan(macd)] = 0
        macdSignal[np.isnan(macdSignal)] = 0
        
        ### 计算后面的值
        mMax = ta.MAX(macd,lagPeriod)
        mMin = ta.MIN(macd,lagPeriod)
        highMax = ta.MAX(barArray.high,lagPeriod)
        lowMin = ta.MIN(barArray.low,lagPeriod)

        ### 计算交叉点
        cross = np.insert((macd[1:]-macdSignal[1:])*(macd[:-1]-macdSignal[:-1])<0,0,False)
        index = np.array([x for x in range(len(cross))])
        macdGap = np.abs(macd-macdSignal)

        signal = 0
        internal = 0
        # ## 判断是否顶背离
        # if cross[-1] and mMax[-1]>0 and np.sum(cross>0)>=2:  # and macd[-1]<macdSignal[-1]:
            
        #     ### 保留最近的交叉点数指标值
        #     mCross1 = mMax[-1]
        #     hCross1 = highMax[-1]
        #     indexNow = index[-1]
            
        #     ### 按照信号筛选交叉点
        #     mMax = mMax[cross]
        #     highMax = highMax[cross]
        #     index = index[cross]
            
        #     for i in range(len(index)-2,0,-1):
        #         if indexNow-index[i]>=minPeriod and mMax[i]>0 and indexNow-index[i]<=maxPeriod:
        #             mCross0 = mMax[i]
        #             hCross0 = highMax[i]
        #             maxGap = np.max(macdGap[-(indexNow-index[i]):-1])
        #             if mCross1 < mCross0 and hCross1 > hCross0 and maxGap>0.002:
        #                 signal = 1 ### 表示顶背离
        #                 internal = indexNow-index[i]
        #             break    
            
        # elif cross[-1] and mMin[-1]<0 and np.sum(cross>0)>=2:  # and macd[-1]>macdSignal[-1]:

        #     ### 保留最近的交叉点数指标值
        #     mCross1 = mMin[-1]
        #     lCross1 = lowMin[-1]
        #     indexNow = index[-1]
            
        #     ### 按照信号筛选交叉点
        #     mMin = mMin[cross]
        #     lowMin = lowMin[cross]
        #     index = index[cross]

        #     for i in range(len(index)-2,0,-1):
        #         if indexNow-index[i]>=minPeriod and mMin[i]<0 and indexNow-index[i]<=maxPeriod:
        #             mCross0 = mMin[i]
        #             lCross0 = lowMin[i]
        #             maxGap = np.max(macdGap[-(indexNow-index[i]):-1])
        #             if mCross1 > mCross0 and lCross1 < lCross0 and maxGap>0.002:
        #                 signal = -1 ### 表示底背离 
        #                 internal = indexNow-index[i]
        #             break
        
        return signal, internal, macd, macdSignal
    
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








        



