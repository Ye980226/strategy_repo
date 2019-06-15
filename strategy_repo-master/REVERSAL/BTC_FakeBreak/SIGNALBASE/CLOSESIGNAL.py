# encoding=utf-8

import talib as ta


# 通过价量关系计算反转出场机会，通常用小周期（15min）以下的bar
def closebyPriceVolumeReverse(am,
                              corrLen=10,
                              exitCorrLong=0.96, exitCorrLongRange=[-0.4, 0.9]):

    '''
    :param am:
    :param corrLen:
    :param exitCorrLong:
    :param exitCorrLongRange:
    :return: sig 0:不出场 1:买平出场 -1:卖平出场
    '''

    corrShort = ta.CORREL(ta.MA(am.low, corrLen), ta.MA(am.volume, corrLen), corrLen)
    corrLong = ta.CORREL(ta.MA(am.high, corrLen), ta.MA(am.volume, corrLen), corrLen)

    sig = 0
    if corrShort[-2] <= corrShort[-1] and corrShort[-2] <= corrShort[-3]:
        sig = 1
    if corrLong[-2] >= corrLong[-1] and corrLong[-2] >= corrLong[-3] and (
            corrLong[-2] >= exitCorrLong or (
            exitCorrLongRange[0] < corrLong[-2] < exitCorrLongRange[1])):
        sig = -1

    return sig
