import talib as ta
import numpy as np

class volumeIndicator:
    def __init__(self, openArray, highArray, lowArray, closeArray, volumeArray):
        self.openArray = openArray
        self.highArray = highArray
        self.lowArray = lowArray
        self.closeArray = closeArray
        self.volumeArray = volumeArray

    def forceIndex(self,t=1):
        '''(C-C1)*V'''
        # giving a buy signal when it crosses above zero and a sell when it crosses below zero
        forceIndex = (self.closeArray[t:]-self.closeArray[:-t])*self.volumeArray[t:]
        return forceIndex

    def volumeMomentum(self, nPeriod = 10):
        '''V-V10'''
        volumeMomentum = self.volumeArray[nPeriod:]-self.volumeArray[:-nPeriod]
        return volumeMomentum

    def volumeMomentumPct(self, nPeriod = 10):
        '''V-V10/V10'''
        volumeMomentumPct = (self.volumeArray[nPeriod:] - self.volumeArray[:-nPeriod])/self.volumeArray[:-nPeriod]
        return volumeMomentumPct

    def volumeDiff(self, shortPeriod = 14, longPeriod = 34):
        '''ADV14-ADV34'''
        volumeDiff = ta.MA(self.volumeArray, shortPeriod)-ta.MA(self.volumeArray, longPeriod)
        return volumeDiff

    def volumeRatio(self, shortPeriod = 14, longPeriod = 34):
        '''SUM(volume,14)/SUM(volume,34)'''
        volumeRatio = ta.SUM(self.volumeArray, shortPeriod)/ta.SUM(self.volumeArray, longPeriod)
        return volumeRatio

    def volumeWvad(self, nPeriod=24):
        wvad = ta.SUM((self.closeArray-self.openArray)/(self.highArray-self.lowArray), nPeriod)
        return wvad

    def volumeAcd(self, nPeriod=20):
        priceUp = [self.closeArray[-i+1] > self.closeArray[-i] for i in range(nPeriod, 0, -1)]
        priceDn = [self.closeArray[-i+1] <= self.closeArray[-i] for i in range(nPeriod, 0, -1)]
        buy = np.array([self.closeArray[-i+1]-min(self.lowArray[-i+1], self.closeArray[-i]) for i in range(nPeriod,0,-1)])*priceUp
        sell = np.array([self.closeArray[-i+1]-max(self.highArray[-i+1], self.closeArray[-i]) for i in range(nPeriod,0,-1)])*priceDn
        power = buy+sell
        ACD = ta.SUM(power,nPeriod-1)
        return ACD

    def volumeObvUpRatio(self, nPeriod = 24):
        '''upObv/downObv'''
        AV = ta.SUM(np.array(self.volumeArray[nPeriod:]*(self.closeArray[nPeriod:]>self.closeArray[:-nPeriod])), nPeriod)
        BV = ta.SUM(np.array(self.volumeArray[nPeriod:]*(self.closeArray[nPeriod:]<=self.closeArray[:-nPeriod])), nPeriod)

        volumeObvUpRatio = AV/BV
        return volumeObvUpRatio

    def volumeObvDownRatio(self, nPeriod = 24):
        '''downObv/upObv'''
        AV = ta.SUM(np.array(self.volumeArray[nPeriod:]*(self.closeArray[nPeriod:]>self.closeArray[:-nPeriod])), nPeriod)
        BV = ta.SUM(np.array(self.volumeArray[nPeriod:]*(self.closeArray[nPeriod:]<=self.closeArray[:-nPeriod])), nPeriod)
        np.seterr(divide='ignore', invalid='ignore')
        volumeObvDownRatio = BV/AV
        return volumeObvDownRatio

    def volumeMfi(self, nPeriod=14):
        '''volume RSI'''
        TP = (self.closeArray+self.highArray+self.lowArray)*self.volumeArray/3
        MFP = ta.SUM(TP[nPeriod:]*(TP[nPeriod:]>TP[:-nPeriod]), nPeriod)
        MFN = ta.SUM(TP[nPeriod:]*(TP[nPeriod:]<=TP[:-nPeriod]), nPeriod)
        MR = MFP/MFN
        volumeMfi = 100-100/(1+MR)
        return volumeMfi

    def volumeCount(self, countBar = 100, t=1):
        '''Sum(Diff(V, V1)/Abs(Diff(V, V1)))'''
        VC = np.array([(self.volumeArray[-i+t]-self.volumeArray[-i])/np.abs(self.volumeArray[-i+t]-self.volumeArray[-i]) for i in range(countBar, 0, -1)])
        VCI = ta.SUM(VC, countBar-t)
        return VCI

    def volumeAccumulator(self, countBar=100):
        '''Sum((C-L)/(H-L)-0.5)*2*V'''
        VA = ((self.closeArray-self.lowArray)/(self.highArray-self.lowArray)-0.5)*2*self.volumeArray
        VAI = ta.SUM(VA, countBar)
        return VAI

    def volumeSpike(self, nPeriod=20, stdMultipler=4):
        '''Find extremely large volume'''
        volumeUpper, volumeMa, _l = ta.BBANDS(self.volumeArray, nPeriod, stdMultipler, stdMultipler)
        return self.volumeArray[nPeriod:]>= (volumeMa+volumeUpper)[nPeriod:]

    def volumeLow(self, nPeriod, stdMultipler=2):
        '''Find extremely small volume'''
        _h, volumeMa, volumeLower = ta.BBANDS(self.volumeArray, nPeriod, stdMultipler, stdMultipler)
        return self.volumeArray[nPeriod:] <= (volumeMa - volumeLower)[nPeriod:]

    def volumeBBands(self, nPeriod, nDev, maType=0):
        volumeUpper, volumeClose, volumeLower = ta.BBANDS(self.volumeArray, nPeriod, nDev, nDev, maType)
        return volumeUpper, volumeClose, volumeLower

    def volumeWeightMacd(self, shortPeriod=12, longPeriod=26):
        '''MACD(volumeWeightClose)'''
        CV = self.closeArray*self.volumeArray
        shortWeightMacd = ta.MA(CV, shortPeriod)/ta.SUM(self.volumeArray, shortPeriod)
        longWeightMacd = ta.MA(CV, longPeriod)/ta.SUM(self.volumeArray, longPeriod)
        volumeWeightMacd = shortWeightMacd-longWeightMacd
        return volumeWeightMacd

    def marketFacilitationIndex(self, nPeriod):
        '''High-Low/Volume'''
        MFI = (ta.MAX(self.highArray, nPeriod)-ta.MIN(self.lowArray, nPeriod))/ta.MA(self.volumeArray, nPeriod)
        return MFI

    def volumePfObv(self, nPeriod=20, stdMultipler=1):
        '''OBV which filter small price change'''
        diff = self.closeArray[1:] - self.closeArray[:-1]
        diffMa = ta.MA(diff, nPeriod)
        stdDev = ta.STDDEV(diff, nPeriod)
        priceThreshold = diffMa+stdMultipler*stdDev
        np.seterr(divide='ignore', invalid='ignore')
        pfVolume = self.volumeArray[1:] * (np.abs(diff) > priceThreshold)
        pfObv = ta.OBV(self.closeArray[1:], pfVolume)
        return pfObv

    def volumePfAd(self, nPeriod=20, stdMultipler=1):
        '''AD which filter small price change'''
        diff = self.closeArray[1:] - self.closeArray[:-1]
        diffMa = ta.MA(diff, nPeriod)
        stdDev = ta.STDDEV(diff, nPeriod)
        priceThreshold = diffMa+stdMultipler*stdDev
        np.seterr(divide='ignore', invalid='ignore')
        pfVolume = self.volumeArray[1:] * (np.abs(diff) > priceThreshold)
        pfAd = ta.AD(self.highArray[1:], self.lowArray[1:], self.closeArray[1:], pfVolume)
        return pfAd

    def AsprayDemandOscillator(self, nPeriod=10):
        maxHigh = [max(self.highArray[i], self.highArray[i+1]) for i in range(nPeriod-1)]
        minLow = [min(self.lowArray[i], self.lowArray[i+1]) for i in range(nPeriod-1)]
        diff = np.array(maxHigh)-np.array(minLow)
        K = (3*self.closeArray[-nPeriod+1:]/(ta.SUM(diff, nPeriod-1)/nPeriod))[-1]
        BP = []
        SP = []
        volumeValues = self.volumeArray[-nPeriod+1:] / K * ((self.closeArray[-nPeriod+1:] - self.closeArray[-nPeriod: -1]) / self.closeArray[-nPeriod: -1])
        for i in range(nPeriod-2):
            if(self.closeArray[-nPeriod+i+1] > self.closeArray[-nPeriod+i]):
                BP.append(self.volumeArray[-nPeriod+i+1])
                SP.append(volumeValues[-nPeriod+i+1])
            else:
                BP.append(volumeValues[-nPeriod+i+1])
                SP.append(self.volumeArray[-nPeriod+i+1])
        DemandOscillator = np.array(BP)-np.array(SP)
        return DemandOscillator

