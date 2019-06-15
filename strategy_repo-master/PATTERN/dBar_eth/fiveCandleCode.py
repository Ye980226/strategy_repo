class candlestick:
    def __init__(self, openArray, highArray, lowArray, closeArray):
        self.openArray = openArray
        self.highArray = highArray
        self.lowArray = lowArray
        self.closeArray = closeArray

    def is_positive(self, n=1):
        """返回True代表过去的第n根k线是上升的"""
        return self.openArray[-n] < self.closeArray[-n]

    def is_negative(self, n=1):
        """返回True代表过去的第n根k线是下降的"""
        return self.openArray[-n] > self.closeArray[-n]

    def entityRate(self, n=1):
        return abs(self.openArray[-n] - self.closeArray[-n]) / (self.highArray[-n] - self.lowArray[-n])

    def checkCandle(self,n=2):
        """"用于检查k线数目，要求array中已存在的大于n数目的k线"""
        if self.closeArray[-n]!=0:
            return True
        else:
            return False

    # 锤头(下影线长度为实体的2倍，设置一般为实体长度较小介于中线实体与小线实体之间)
    def candleHammer(self, minShadowPct=0.005):
        """返回1收阳线，返回-1收阴线"""
        entity = self.entityRate()
        candleStatus = 0
        if self.is_positive():
            uplineRate = (self.highArray[-1]-self.closeArray[-1])/(self.highArray[-1]-self.lowArray[-1])
            downlineRate = (self.openArray[-1]-self.lowArray[-1])/(self.highArray[-1]-self.lowArray[-1])
            candleStatus = 1 if downlineRate>=2*entity and uplineRate<=minShadowPct else 0
        elif self.is_negative():
            uplineRate = (self.highArray[-1]-self.openArray[-1])/(self.highArray[-1]-self.lowArray[-1])
            downlineRate = (self.closeArray[-1]-self.lowArray[-1])/(self.highArray[-1]-self.lowArray[-1])
            candleStatus = -1 if downlineRate>=2*entity and uplineRate<=minShadowPct else 0
        return candleStatus

    # 倒锤头(上影线长度为实体的两倍以上，设置实体较小，下影线较短或者没有)
    def candleInvertedHammer(self, minShadowPct=0.005):
        """返回1收阳线，返回-1收阴线"""
        entity = self.entityRate()
        candleStatus = 0
        if self.is_positive():
            uplineRate = (self.highArray[-1] - self.closeArray[-1]) / (self.highArray[-1] - self.lowArray[-1])
            downlineRate = (self.openArray[-1] - self.lowArray[-1]) / (self.highArray[-1] - self.lowArray[-1])
            candleStatus = 1 if uplineRate>=2*entity and downlineRate<=minShadowPct else 0
        elif self.is_negative():
            uplineRate = (self.highArray[-1] - self.openArray[-1]) / (self.highArray[-1] - self.lowArray[-1])
            downlineRate = (self.closeArray[-1] - self.lowArray[-1]) / (self.highArray[-1] - self.lowArray[-1])
            candleStatus = -1 if uplineRate>=2*entity and downlineRate<=minShadowPct else 0
        return candleStatus

    # 高浪线： 实体占k线小，上下影线长
    def candleHighWave(self, minEntityRate=0.01, minShadowPct=0.015):
        """返回1收阳线，返回-1收阴线"""
        entity = self.entityRate()
        candleStatus = 0
        if entity<=minEntityRate:
            if self.is_positive() :
                uplineRate = (self.highArray[-1]-self.closeArray[-1])/(self.highArray[-1]-self.lowArray[-1])
                downlineRate = (self.openArray[-1]-self.lowArray[-1])/(self.highArray[-1]-self.lowArray[-1])
                candleStatus = 1 if uplineRate>=minShadowPct and downlineRate>=minShadowPct else 0
            elif self.is_negative():
                uplineRate = (self.highArray[-1]-self.openArray[-1])/(self.highArray[-1]-self.lowArray[-1])
                downlineRate = (self.closeArray[-1]-self.lowArray[-1])/(self.highArray[-1]-self.lowArray[-1])
                candleStatus = -1 if uplineRate>=minShadowPct and downlineRate>=minShadowPct else 0
        return candleStatus

    #############两根bar#################
    # 吞噬： 最近的一根Bar高低价吞噬前一根Bar不需要开收价吞噬
    def candleEngulfing(self, preMinBarPct=0.008, postMinBarPct = 0.01):
        """返回1看涨吞噬先跌后涨，返回-1看跌吞噬先涨后跌"""
        prePositive = self.is_positive(n=2)
        preNegative = self.is_negative(n=2)
        higherHigh = self.highArray[-1] > self.highArray[-2]
        lowerLow = self.lowArray[-1] < self.lowArray[-2]
        candleStatus = 0
        if higherHigh and lowerLow:
            if preNegative:
                preShort = self.openArray[-2]/self.closeArray[-2]-1
                postLong = self.closeArray[-1]/self.openArray[-1]-1
                candleStatus = 1 if preShort>=preMinBarPct and postLong>=postMinBarPct else 0
            elif prePositive:
                preLong = self.closeArray[-2]/self.openArray[-2]-1
                postShort = self.openArray[-1]/self.closeArray[-1]-1
                candleStatus = -1 if preLong>=preMinBarPct and postShort>=postMinBarPct else 0
        return candleStatus

    # 乌云盖顶： 创了新低或新高后反弹回上一根Bar的一半以上
    def candleDarkCloudCover(self, preMinBarPct=0.01):
        """返回1先跌创新低后涨，返回-1先涨创新高后跌"""
        prePositive = self.is_positive(n=2)
        preNegative = self.is_negative(n=2)
        higherHigh = self.highArray[-1] > self.highArray[-2]
        lowerLow = self.lowArray[-1] < self.lowArray[-2]
        candleStatus = 0
        if preNegative and lowerLow:
            preShort = self.openArray[-2]/self.closeArray[-2]-1
            postLong = self.closeArray[-1]/self.openArray[-1]-1
            candleStatus = 1 if preShort>=preMinBarPct and postLong>=(preMinBarPct/2) else 0
        elif prePositive and higherHigh:
            preLong = self.closeArray[-2]/self.openArray[-2]-1
            postShort = self.openArray[-1]/self.closeArray[-1]-1
            candleStatus = -1 if preLong>=preMinBarPct and postShort>=(preMinBarPct/2) else 0
        return candleStatus

    # CambridgeHook
    def cambridgeHook(self):
        """
        LongEntry: a lower low followed by a higher close
        ShortEntry: a higher high followed by a lowerer close
        """
        candleStatus = 0   
        if self.lowArray[-1] < self.lowArray[-2] and self.closeArray[-1] > self.closeArray[-2]:
            candleStatus = 1
        elif self.highArray[-1] > self.highArray[-2] and self.closeArray[-1] < self.closeArray[-2]:
            candleStatus = -1
        return candleStatus

    # doubeBar
    def candledoublebar(self,shrink1=0.8,shrink2=100):
        """
        1、两根bar方向相同，
        2、第二根bar的引线不能超过第二根实体的shrink1,
        3、第二根bar的实体不能超过第一根实体的shrink2
        """
        candlestick = 0
        if self.is_negative(2) and self.is_negative(1) \
        and self.closeArray[-1]-self.lowArray[-1]<(self.openArray[-1]-self.closeArray[-1])*shrink1:
            if self.openArray[-1]-self.closeArray[-1]<(self.openArray[-2]-self.closeArray[-2])*shrink2:
                candlestick = -1
            else:
                candlestick = -2
        elif self.is_positive(2) and self.is_positive(1) \
        and self.highArray[-1]-self.closeArray[-1]<(self.closeArray[-1]-self.openArray[-1])*shrink1:
            if self.closeArray[-1]-self.openArray[-1]<(self.closeArray[-2]-self.openArray[-2])*shrink2:
                candlestick = 1
            else:
                candlestick = 2
        return candlestick
