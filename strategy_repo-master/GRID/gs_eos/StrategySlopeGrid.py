import numpy as np
import talib as ta
from datetime import timedelta, datetime
import time
from vnpy.trader.utils.templates.orderTemplate import *
from calEnv import CalEnv
calEnv = CalEnv()


'''
使用移动止损的办法控制出场
2019年2月15日 10:25:29
每当价格按照理想的方向移动self.addPercent，对应的止损也移动self.addPercent

2019年2月19日 15:54:11
过滤掉最近有极端行情的bar
'''

########################################################################
class StrategySlopeGrid(OrderTemplate):
    
    className = 'StrategySlopeGrid'
    author = 'zong'

    # 同步列表，保存了需要保存到数据库的变量名称
    syncList = ['posDict', 'eveningDict']
    # 参数列表，保存了参数的名称
    paramList = [
        'symbolList',
        'posSize',
        'maxlines',

        #### 一些会用到的变量 ###
        'estimateWindow',   ## 滚动估计takeProfit时使用的窗口， 小时
        'leaveMax',         ## 当价格突破leaveMax的极值时平掉所有同乡的单， 小时
        'openPeriod',       ## 价格距离openPeriod只有不到openGap的距离时不开单
        'openGap',          ## 价格距离openPeriod只有不到openGap的距离时不开单
        'slopethreshold',   ## 当斜率超过这个阈值是网格转为只在上方开空只在下方开多，同时调整止盈位置 

        ### 时间周期
        'stopLoss',          ## 百分比止损
        'takeProfit',        ## 百分比止盈
        'timeframeMap'       ## 默认变量
        ]
    # ----------------------------------------------------------------------
    def __init__(self, ctaEngine, setting):
        super().__init__(ctaEngine, setting)
        print(setting) 
        self.writeCtaLog(str(setting))
        self.symbol = setting['symbolList'][0]
        
        ### 内部存贮订单并管理的字典
        self.orderDict = {}
        self.posbuyArray = np.zeros((15,10))
        self.posshortArray = np.zeros((15,10))
        ### 防止重复去寻找低频bar
        self.lastKlineTime = {
            i:None for i in self.timeframeMap
        }

        ### 内部记录仓位 ###
        self.buyPos, self.shortPos = 0, 0

    # ----------------------------------------------------------------------
    def perpare_date(self):
        """
        注册bar事件，不需要特别推送，但需要获得对应的k线
        """
        for timeframe in self.timeframeMap:
            self.registerOnBar(self.symbol,timeframe,None)
    
    # --------------------------------------------------------------------
    def barPrepared(self, period):
        """
        判断是否产生了个新bar——有新bar则进行信号计算
        """
        am = self.getArrayManager(self.symbol, period)
        if not am.inited:
            self.writeCtaLog("am is not inited:%s" % (period,))
            return False, None
        if self.lastKlineTime[period] is None or am.datetime[-1] > self.lastKlineTime[period]:
            return True, am
        else:
            return False, None

    # --------------------------------------------------------------------
    def updateLastKlineTime(self):
        """更新K线时间"""
        for period in self.timeframeMap:
            self.lastKlineTime[period] = self.getArrayManager(self.symbol, period).datetime[-1]


    # ----------------------------------------------------------------------
    def onInit(self):
        """初始化策略"""
        self.setArrayManagerSize(1000)
        self.perpare_date()
        self.putEvent()

    # ----------------------------------------------------------------------
    def onStart(self):
        """启动策略（必须由用户继承实现）"""
        self.putEvent()

    # ----------------------------------------------------------------------
    def onStop(self):
        """停止策略（必须由用户继承实现）"""
        self.putEvent()

    # ----------------------------------------------------------------------
    def onTick(self, tick):
        """收到行情TICK推送"""
        super().onTick(tick)
        pass
    
    # ---------------------------------------------------------------------
    def on5sBar(self,bar):
        """
        实盘中在10秒bar里面洗价
        """
        super().onBar(bar)
        self.checkOnPeriodStart(bar)
        #--------------------------------------------
        self.delOrderID() 
        # -------------------------------------------
        self.checkOnPeriodEnd(bar)
        pass

    # ------------------------------------------------------------------------
    def delOrderID(self):
        """
        从self.OrderDict中删除已经完成的订单
        """
        for vtOrderID in list(self.orderDict):
            op = self._orderPacks[vtOrderID]
            if self.orderClosed(op):
                ### 将对应的posbuyArray或priceshortarray重新变成0
                r,c = self.orderDict[vtOrderID]['row'], self.orderDict[vtOrderID]['col']
                if self.orderDict[vtOrderID]['type']=='buy':
                    self.posbuyArray[r][c] = 0
                else:
                    self.posshortArray[r][c] = 0
                ### 从orderDict中删除
                del self.orderDict[vtOrderID]

    # --------------------------------------------------------------------
    def getlocalPos(self):
        """计算总的仓位，需要控制总的仓位不超过某个值"""
        buyPos, shortPos = 0, 0
        for vtOrderID in self.orderDict:
            op = self._orderPacks.get(vtOrderID, None)
            openVolume = op.order.tradedVolume 
            closedVolume = self.orderClosedVolume(op)  
            if op.order.direction == DIRECTION_LONG:
                buyPos += (openVolume - closedVolume)
            else:
                shortPos += (openVolume - closedVolume)
        self.buyPos = buyPos
        self.shortPos = shortPos

    # --------------------------------------------------------------------
    def onBar(self,bar):
        super().onBar(bar)
        if self.getEngineType() == 'backtesting':
            self.checkOnPeriodStart(bar)
            #--------------------------------------------
            self.delOrderID() 
            # -------------------------------------------
            self.checkOnPeriodEnd(bar)
        
        ### 打印当前持仓量 
        self.getlocalPos()
        self.writeCtaLog('current long pos hold:%s, short pos hold:%s'%(self.buyPos, self.shortPos))
        #### 执行策略逻辑
        self.strategy(bar)
           
    # ---------------------------------------------------------------------
    def strategy(self,bar):
        """
        策略逻辑主体，设置指标计算，信号组装，环境判断和下单
        """
        #### 根据出场信号出场
        exitSignal,high,low = self.exitSignal(bar)
        self.exitOrder(exitSignal,high,low,bar)
        #### 根据信号进场
        entrySignal = self.entrySignal(bar)
        self.entryOrder(entrySignal,bar)
        #### 更新lastBarTime
        self.updateLastKlineTime()
        

    # --------------------------------------------------------------------
    def exitSignal(self,bar):
        """平仓信号"""
        exitSignal = 0
        am = self.getArrayManager(bar.vtSymbol,'1h')
        high = np.max(am.high[-self.leaveMax:])
        low =  np.min(am.low[-self.leaveMax:]) 
        if bar.high > high:
            exitSignal = -1
        elif bar.low < low:
            exitSignal = 1   
        self.writeCtaLog('exitlineCheck, datetime:%s,high:%s,low:%s'%(am.datetime[-self.leaveMax],high,low))
        return exitSignal, high, low

    # ---------------------------------------------------------------------
    def exitOrder(self,exitSignal, high,low,bar):
        """"平仓"""
        for vtOrderID in self.orderDict:
            op = self._orderPacks[vtOrderID]
            if op:
                if op.order.direction == DIRECTION_LONG and exitSignal==1:
                    self.composoryClose(op)
                elif op.order.direction == DIRECTION_SHORT and exitSignal==-1:
                    self.composoryClose(op)
        
    # ----------------------------------------------------------------------
    def entrySignal(self,bar):
        """计算发单信号"""
        return True

    # ---------------------------------------------------------------------
    def entryOrder(self,entrySignal,bar):
        """
        得到信号后判断能否下单
        """
        if not entrySignal:
            return
        
        TF ,_ = self.barPrepared('15m')
        if not TF:
            return

        if self.getEngineType() == 'trading':
            volume = self.posSize
        else:
            volume = self.posSize/bar.close

        ### 获得openHigh和openLow
        openhigh, openlow = self.getopenhighandopenlow(self.openPeriod,bar,'1h')
        ### 获得midlane
        _, midlane, _, shortadd, buyadd = self.getmidlane(self.estimateWindow,bar,'15m')
        ### 获得斜率指标
        am1h = self.getArrayManager(bar.vtSymbol, '1h')
        _, slope = calEnv.trendcheck(am1h)
        
        ### 获取目前在外面的所有单的开仓价格，同方向价格相近的不在开单
        buyPriceList, shortPriceList = self.priceList()        
        ##### 挂出买单 ####
        self.buySendOrder(slope,midlane,buyPriceList,buyadd,openhigh=openhigh,openlow=openlow,bar=bar,volume=volume)
        ##### 挂出卖单 ####
        self.shortSendOrder(slope,midlane,shortPriceList,shortadd,openhigh=openhigh,openlow=openlow,bar=bar,volume=volume)
       
    # ---------------------------------------------------------------------
    def priceList(self):
        """获得当前持仓和挂单的所有开仓价"""
        buyPrice, shortPrice = [], []
        for value in self.orderDict.values():
            if value['type'] == 'buy':
                buyPrice.append(value['price'])
            else:
                shortPrice.append(value['price'])
        return buyPrice, shortPrice        

    # ----------------------------------------------------------------------
    def getopenhighandopenlow(self,openPeriod,bar,barPeriod='1h'):
        """获得openhigh和openlow"""
        am1h = self.getArrayManager(bar.vtSymbol,barPeriod)
        am60 = self.getArrayManager(bar.vtSymbol,'1m')
        openhigh = max(np.max(am1h.high[-openPeriod:]),np.max(am60.high[-60:]))
        openlow = min(np.min(am1h.low[-openPeriod:]),np.min(am60.low[-60:]))
        return openhigh, openlow

    # ---------------------------------------------------------------------
    def getmidlane(self,period,bar,barPeriod='15m'):
        """计算midlane等价格指标"""
        am = self.getArrayManager(bar.vtSymbol, barPeriod)
        lowlane, highlane = np.min(am.low[-period:]), np.max(am.high[-period:])
        midlane = (highlane+lowlane)/2
        shortadd = max((highlane - midlane)*0.1,bar.close*5/1000)
        buyadd = max((midlane-lowlane)*0.1,bar.close*5/1000) 
        return highlane, midlane, lowlane, shortadd, buyadd

    # ----------------------------------------------------------------------
    def pricein(self,price,priceList,rate=5/1000):
        """如果price在pricelist中某个价格的上下0.005范围之中则返回False"""
        for exitprice in priceList:
            if price>exitprice*(1-rate) and price<exitprice*(1+rate):
                return False
        return True

    # ------------------------------------------------------------------------
    def buySendOrder(self,slope, midlane, buyPriceList, buyadd, openhigh, openlow,bar,volume,maxt=2):
        """发多单逻辑"""
        if np.sum(self.posbuyArray) >= self.maxlines:
            return
        t = 1
        for r in range(0,self.posbuyArray.shape[0]):
            ### 首先判断在这个位置是否已经开满单
            c = np.sum(self.posbuyArray[r]>0.1)
            ### 根据斜率和r的大小设置不同的止盈
            k=4 if slope>-self.slopethreshold else 0
            price = midlane-(r-k)*buyadd
            p = 1 if r-k<=1 else r-k
            if np.sum(self.posbuyArray[r]<0.1)==0:
                continue
            ### 价格在网的上方才开单，然后记录订单价格等信息
            if bar.close > price and price > openlow*(1+self.openGap) and price < openhigh*(1-self.openGap):  
                if self.pricein(price,buyPriceList) and t<=maxt:
                    t += 1
                    tlo = self.timeLimitOrder(ctaBase.CTAORDER_BUY,bar.vtSymbol,price,volume,14*60)
                    self.writeCtaLog('grid buy price%s,otherinfo k:%s,openGap:%s,%s'%(price,k,openlow*(1+self.openGap),openhigh*(1-self.openGap)))
                    for vtOrderID in tlo.vtOrderIDs:
                        self.orderDict[vtOrderID] = {'type':'buy','price':price,'row':r,'col':c}
                        self.posbuyArray[r][c]=1
                        op = self._orderPacks.get(vtOrderID, None)
                        self.setAutoExit(op,stoploss=(1-self.stopLoss)*price,takeprofit=price*(1+p*self.takeProfit))

    # ---------------------------------------------------------------------------------------
    def shortSendOrder(self,slope,midlane,shortPriceList, shortadd, openhigh, openlow, bar,volume,maxt=2):
        """发空单逻辑"""
        if np.sum(self.posshortArray) >= self.maxlines:
            return
        t = 1
        for r in range(0,self.posshortArray.shape[0]):
            ### 首先判断在这个位置是否已经开满单
            c = np.sum(self.posshortArray[r]>0.1)
            ### 根据斜率和r的大小设置不同的止盈
            k = 4 if slope<self.slopethreshold else 0
            price = midlane+(r-k)*shortadd  
            p = 1 if r-k<=1 else r-k
            if np.sum(self.posshortArray[r]<0.1)==0:
                continue
            ### 价格在网的上方才开单，然后记录订单价格等信息
            if bar.close < price and price > openlow*(1+self.openGap) and price < openhigh*(1-self.openGap):
                if self.pricein(price, shortPriceList) and t <=maxt:
                    t+=1               
                    tlo = self.timeLimitOrder(ctaBase.CTAORDER_SHORT,bar.vtSymbol,price,volume,14*60)
                    self.writeCtaLog('grid short price%s,otherinfo k:%s,openGap:%s,%s'%(price,k,openlow*(1+self.openGap),openhigh*(1-self.openGap)))
                    for vtOrderID in tlo.vtOrderIDs:
                        self.orderDict[vtOrderID] = {'type':'short','price':price,'row':r,'col':c}
                        self.posshortArray[r][c]=1  
                        op = self._orderPacks.get(vtOrderID,None)
                        self.setAutoExit(op,stoploss=(1+self.stopLoss)*price,takeprofit=price*(1-p*self.takeProfit))  
