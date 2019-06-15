# encoding=utf-8

import talib as ta


# 根据ADX指标判断当前是否是趋势环境，通常用30分钟bar以上的大周期
def isTrendbyADX(am, ADXLen=55, ADXThreshold=25):
    '''
    :param am: arrayManager
    :param ADXLen: 计算ADX的bar长度,int
    :param ADXThreshold: 用于判断趋势环境的ADX的阈值,设置的越小更倾向于判断成趋势行情，float
    :return: True--是趋势，False--不是趋势
    '''

    return ta.ADX(am.high, am.low, am.close, ADXLen)[-1] > ADXThreshold


# 根据ATR指标判断当前的波动率是否足够，通常用小周期（15min）以下的bar
def haveEnoughVolbyATR(am, ATRLen=20, ATRMALen=20, minATRLimit=0.003):
    '''
    :param am: arrayManager
    :param ATRLen: 计算ATR的bar长度,int
    :param ATRMALen: 计算一段时间ATR均值的ATR序列长度,int
    :param minATRLimit: 用于判断当前波动空间是否足够的阈值,设置的越小更倾向于判断波动足够，float
    :return:
    '''
    ATR = ta.ATR(am.high, am.low, am.close, ATRLen) / am.close[-1]
    ATRMA = ta.EMA(ATR, ATRMALen)
    return ATR[-1] >= ATRMA[-1] and ATR[-1] >= minATRLimit
