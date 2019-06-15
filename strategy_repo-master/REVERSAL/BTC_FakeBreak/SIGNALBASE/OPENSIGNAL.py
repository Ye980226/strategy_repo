# encoding=utf-8

import talib as ta


# 通过价量关系计算反转开仓机会，通常用小周期（15min）以下的bar
def openbyPriceVolumeReverse(am,
                             corrLen=10,
                             posRange=[5, 25], negDirPctRange=[0.002, 0.025], sameDirPctLimit=0.005,
                             minCorrLong1=-0.85, minCorrLong2=-0.95, minCorrShort1=0.28,
                             holdingBuyOP=False, holdingShortOP=False):

    '''
    :param am: arrayManager
    :param corrLen: 用n根bar计算价量相关性指标, int
    :param posRange: 计算近期收益变化的bar数的范围要求 [int1,int2]
    :param negDirPctRange: 与信号方向相反的近期收益范围要求（不能太大也不能太小，保持一定的波动性）[float1,float2]
    :param sameDirPctLimit: 与信号方向相同的近期收益最大值（不能太大，否则追进去风险比较高）float
    :param minCorrLong1:  多头开仓的阈值1 float
    :param minCorrLong2:  多头开仓的阈值2 float
    :param minCorrShort1: 空头开仓的阈值1 float
    :param holdingBuyOP:  当前持有多头仓位 bool
    :param holdingShortOP: 当前持有空头仓位 bool
    :return: sig 0:不开仓 1:开多头 -1:开空头
    '''

    corrShort = ta.CORREL(ta.MA(am.low, corrLen), ta.MA(am.volume, corrLen), corrLen)
    corrLong = ta.CORREL(ta.MA(am.high, corrLen), ta.MA(am.volume, corrLen), corrLen)

    def findPos(Series):
        pos = []
        for i in range(2, len(Series)):
            if (Series[-i] <= 0) ^ (Series[-i - 1] <= 0):
                pos.append(i)
            if len(pos) >= 2:
                break
        if len(pos) < 2:
            pos.append(None)
        return pos

    def getPos_Range(corrShort, minPos=6, maxPos=27):
        riseRange = None
        fallRange = None
        _pos = findPos(corrShort)
        pos = None
        if _pos[0] >= 6:
            pos = _pos[0]
        elif _pos[1] is not None and _pos[1] >= minPos:
            pos = _pos[1]
        if pos is not None and _pos[1] is not None and _pos[1] < maxPos:
            riseRange = am.close[-1] / am.open[-pos:].min() - 1
            fallRange = am.close[-1] / am.open[-pos:].max() - 1
        return riseRange, fallRange, _pos

    buysig = 0
    if corrLong[-1] > corrLong[-2] and corrLong[-3] > corrLong[-2] > minCorrLong2 and \
            corrLong[-1] > minCorrLong1:
        riseRange, fallRange, _pos = getPos_Range(corrShort, posRange[0], posRange[1])
        if riseRange is not None:
            if riseRange < sameDirPctLimit and \
                    -negDirPctRange[1] < fallRange <= -negDirPctRange[0] and not holdingShortOP:
                buysig = 1

    shortsig = 0
    if corrShort[-1] > minCorrShort1 and corrShort[-2] < 0:
        # 定位涨幅统计区间
        riseRange, fallRange, _pos = getPos_Range(corrShort, posRange[0], posRange[1])
        if riseRange is not None:
            if fallRange > -sameDirPctLimit and \
                    negDirPctRange[1] > riseRange >= negDirPctRange[0] and \
                    corrShort[-_pos[1]:-1].max() >= 0.5 and not holdingBuyOP:
                shortsig = -1

    sig = buysig + shortsig

    return sig
