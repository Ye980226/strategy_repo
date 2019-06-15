# encoding: UTF-8

"""
套利策略
策略版本 1.1.1
vnpy版本 1.1.12

和实盘中运行的实际策略不同，为了避免20049错误，
测试策略只运行了3条线中的2条
"""

from vnpy.trader.vtConstant import *
# EMPTY_STRING, DIRECTION_LONG, DIRECTION_SHORT,OFFSET_OPEN, OFFSET_CLOSE,
# STATUS_CANCELLED,STATUS_NOTTRADED,STATUS_PARTTRADED,STATUS_ALLTRADED
from vnpy.trader.app.ctaStrategy.ctaTemplate import (CtaTemplate,
                                                     BarGenerator,
                                                     ArrayManager)

from collections import defaultdict
import numpy as np
import talib as ta
import time
from datetime import datetime
########################################################################
class FishingNoramlStrategy(CtaTemplate):
    """配对交易策略"""
    className = 'FishingNoramlStrategy'
    author = 'zongzong'
    version = '1.1.12'
    SettingVersion = '初始后获得'
    
    # 策略交易标的
    #symbolList = []                 # 初始化为空
    activeSymbol = EMPTY_STRING     # 主动品种
    passiveSymbol = EMPTY_STRING    # 被动品种
    activelong = EMPTY_STRING        # 主动品种多仓
    activeshort = EMPTY_STRING       # 主动品种空仓
    passivelong = EMPTY_STRING        # 被动品种多仓
    passiveshort = EMPTY_STRING       # 被动品种空仓
    posDict = {}                    # 仓位数据缓存
    eveningDict = {}                # 可平仓量数据缓存
    bondDict = {}                   # 保证金数据缓存

    
    #初始化均值和标准差

    # 策略参数
    reform = 0    # 和reforming相关联的计数器 
    posSize = 1
    maxstatus = 100 #所有方向可以持有的最多仓位+已挂出单数量
    status = [0,0] #status[0]表示 long_active_short_passive的理论持仓，status[1]表示 short_active_long_passive的理论持仓
    lagtime = 120  # mins

    # 策略变量

    spreadBand = 0.1     # 进价差的阈值，在次加入gap下限价单
    spreadclose = 0.2    # 出场差的阀值，在次先判断盘口，如果盘口好立刻市价出场
    waitlen = 20     # 每隔几个tick进行一次撤单并重新判断入场
    let = 0    # 对应waitlen的计数器
    maxcost = 2     # 能接受的最大交易成本
    maxaskbid = 0.3  # 出场能接受的最大ask-bid-spread
    spreadBuffer = []  # 缓存计算得到的价差
    miu_short = 0  # 缓存短期价差均值
    miu_short_list = []  # 将短期价差均值存入一个list
    miu_long = 0   # 缓存长期价差均值
    miu_long_list = []  # 将长期价差均值存入一个list
    std = 0   # 短期标准差
    spread = 0  # 价差
    gap = 0   # 入场阈值
    levelRate = 10  # 杠杆倍数
    stopLost = 0  # 是否止损标志

    pos = 0   # 内部缓存仓位标志
    change_miu = 0  # 是否更换价格均值标志
    
    # 参数列表，保存了参数的名称
    paramList = ['name',
                 'className',
                 'author',
                 'version',
                 'SettingVersion',
                 'activeSymbol',
                 'passiveSymbol',
                 'spreadBand',
                'maxaskbid',
                'spreadclose',
                'gap',
                'pos']

    # 变量列表，保存了变量的名称
    varList = ['inited',
               'trading',
               'posDict',
               'miu_short',
               'miu_long',
               'std',
               'posSize',
               'reform',
               'spreadBand',
               'maxcost']

    # 同步列表，保存了需要保存到数据库的变量名称
    syncList = ['posDict',
                'eveningDict',
                'bondDict']

    # ----------------------------------------------------------------------
    def __init__(self, ctaEngine, setting):
        """Constructor"""
        super(FishingNoramlStrategy, self).__init__(ctaEngine, setting)
        self.go = float(setting['para'][0])
        self.go2 = float(setting['para'][1])
        self.mintick = float(setting['para'][2])   
        self.posSize = float(setting['posSize'])
        # self.length = float(setting['length'])
        self.lagtime = int(setting['lagtime'])
        self.levelRate = int(setting['levelRate'])
        self.SettingVersion = setting['version']
        print('##################',self.go,self.go2,self.posSize)
        self.maxpos = self.posSize*3

    # ----------------------------------------------------------------------
    def onInit(self):
        """初始化策略（必须由用户继承实现）"""
        self.writeCtaLog(u'%s策略初始化' % self.name)
        
	    #vtSymbolset=setting['vtSymbol']        # 读取交易品种  
        self.activeSymbol = self.symbolList[0]    # 主动品种
        self.passiveSymbol = self.symbolList[1]   # 被动品种
        #self.symbolList = [self.activeSymbol, self.passiveSymbol]
        
        self.generateHFBar(3)
       
        # 创建K线合成器对象
        self.bgDict = {
            sym: BarGenerator(self.onBar)
            for sym in self.symbolList
        }
        
        # 创建数组容器
        self.amDict = {
            sym: ArrayManager()
            for sym in self.symbolList
        }

        self.bg5Dict = {
            sym: BarGenerator(self.onBar,5,self.on5MinBar)
            for sym in self.symbolList
        }
        
        # 创建数组容器
        self.am5Dict = {
            sym: ArrayManager()
            for sym in self.symbolList
        }

        # 创建tick数据缓存容器
        self.tickBufferDict = {
            sym: []
            for sym in self.symbolList
        }
        
        self.datetime = {self.activeSymbol:0,self.passiveSymbol:0}

        self.limitOrderDict = {}   
        self.closeOrderDict = {}
        self.lastminOrderDict = {}
        self.stopActiveID, self.stopPassiveID = None, None
        # 'price', 'direction', 'offset'
        self.lastPriceDict = {sym:[] for sym in self.symbolList}
        self.askbidVolumeDict = {sym:[] for sym in self.symbolList}
        #

        self.reform = 0
        self.reform2 = 0


        # 载入历史数据，并采用回放计算的方式初始化策略数值
        pastbar1 = self.loadHistoryBar(self.activeSymbol,
                            type_ = "1min", 
                            size = 1500)

        pastbar2 = self.loadHistoryBar(self.passiveSymbol,
                        type_ = "1min",
                        size = 1500)
        temp3 = []

        for bar1,bar2 in zip(pastbar1,pastbar2):
            self.amDict[self.activeSymbol].updateBar(bar1)
            self.amDict[self.passiveSymbol].updateBar(bar2)
            self.spreadBuffer.append(bar1.close-bar2.close)
            print(bar1.datetime,bar2.datetime,bar1.close-bar2.close)
            temp3.append(bar1.close+bar2.close)
      
        #获得初始的miu_short和miu_long
        self.miu_short = np.mean(np.array(self.spreadBuffer[-self.lagtime:]))
        self.std = np.std(np.array(self.spreadBuffer[-self.lagtime:]))
        self.miu_short_list.append(self.miu_short)
        self.miu_long = np.mean(np.array(self.spreadBuffer[-3*self.lagtime:]))
        self.miu_long_list.append(self.miu_long)
        summean = np.mean(np.array(temp3[-60:]))/2

        self.gap = max(self.go*summean,2*self.std)
        self.gapadd = 0.001*summean 
        self.spreadBand = 0.0005*summean
        self.spreadcloseold = self.go2*summean
        self.spreadclosenew = -self.gap + 0.004*summean  # 千分之四刚刚好弥补手续费
        self.spreadclose = self.spreadcloseold
        print(summean, self.gap, self.spreadclose)

        self.writeCtaLog('CTAsetting version:%s, Strategy version:%s'%(self.SettingVersion,self.version))

        # 当长期均值和短期均值差异大时更改gap
        if abs(self.miu_long-self.miu_short) > self.gap:
            self.gap = abs(self.miu_long-self.miu_short)
            self.writeCtaLog(u'价差变化过快，请谨慎交易')
        
        self.writeCtaLog('初始的miu_short：%s, miu_long:%s, gap:%s'%(self.miu_short,self.miu_long,self.gap))
        self.opentime = datetime.now()
        self.writeCtaLog('opentime:%s'%self.opentime)
        self.putEvent()

    # ----------------------------------------------------------------------
    def onStart(self):
        """启动策略（必须由用户继承实现）"""
        self.writeCtaLog(u'%s策略启动' % self.name)
        # self.ctaEngine.loadSyncData(self)
        self.pos = self.posDict[self.activeSymbol+'_LONG']
        self.writeCtaLog(u'pos equals to %s'%self.pos)
        self.putEvent()

    # ----------------------------------------------------------------------
    def onStop(self):
        """停止策略（必须由用户继承实现）"""
        self.writeCtaLog(u'%s策略停止' % self.name)
        # self.mail(u'strategy stop: %s'%self.name)
        self.putEvent()

    # ----------------------------------------------------------------------
    def onTick(self, tick):
        """收到行情TICK推送"""
   
        # print(self.lagtime)
        self.bgDict[tick.vtSymbol].updateTick(tick)
        self.hfDict[tick.vtSymbol].updateTick(tick)
        self.tickBufferDict[tick.vtSymbol].append(tick)
        self.lastPriceDict[tick.vtSymbol].append(tick.lastPrice)
        self.askbidVolumeDict[tick.vtSymbol].append(tick.askVolume1+tick.bidVolume1)

        # if self.pos != 0:
        #     midPassive = (self.tickBufferDict[self.passiveSymbol][-1].askPrice1 + self.tickBufferDict[self.passiveSymbol][-1].bidPrice1)/2
        #     midActive = (self.tickBufferDict[self.activeSymbol][-1].askPrice1 + self.tickBufferDict[self.activeSymbol][-1].bidPrice1)/2
        #     self.writeCtaLog(u'midspread:%s, uplevel:%s, downlevel:%s, ask:%s, bid:%s'%
        #     (midActive-midPassive,self.miu_short+self.gap, self.miu_short-self.gap,
        #     tick.askVolume1,tick.bidVolume1)) 

        #控制self.tickBufferDict的长度防止过长占用内存
        if len(self.tickBufferDict[self.activeSymbol]) > 20000:
            self.tickBufferDict[self.activeSymbol] = self.tickBufferDict[self.activeSymbol][-10000:]
            self.tickBufferDict[self.passiveSymbol] = self.tickBufferDict[self.passiveSymbol][-10000:]
        
        # if len(self.limitOrderDict) > 5:
        #     self.writeCtaLog(u'limitOrderDict长度超过10，异常终止策略')
        #     self.onStop()
        ###################################################################################
        # 同步数据到数据库
#         self.saveSyncData()
        # 发出状态更新事件
        if self.stopLost == 1:
            if len(self.limitOrderDict.keys()) > 0:
                for order in self.limitOrderDict.keys():
                    self.cancelOrder(order)
                    self.writeCtaLog(u'撤销%s'%(order))
            else:
                activeprice = self.tickBufferDict[self.activeSymbol][-1].lastPrice
                passiveprice = self.tickBufferDict[self.passiveSymbol][-1].lastPrice
                if self.pos > 0:
                    ### 平掉主动多仓和被动空仓
                    self.stopActiveID = self.sell(self.activeSymbol,activeprice,abs(self.pos),priceType = PRICETYPE_MARKETPRICE,levelRate = self.levelRate)[0]
                    self.stopPassiveID = self.cover(self.passiveSymbol,passiveprice,abs(self.pos),priceType = PRICETYPE_MARKETPRICE,levelRate = self.levelRate)[0]
                elif self.pos < 0:
                    ### 平掉主动空仓和被动多仓
                    self.stopActiveID = self.cover(self.activeSymbol,activeprice,abs(self.pos),priceType = PRICETYPE_MARKETPRICE,levelRate = self.levelRate)[0]
                    self.stopPassiveID = self.sell(self.passiveSymbol,passiveprice,abs(self.pos),priceType = PRICETYPE_MARKETPRICE,levelRate = self.levelRate)[0]                    
            if self.stopActiveID == 'Done' and self.stopPassiveID == 'Done':
                ### 重新估计参数，重新开始交易
                self.stopLost = 0                 
                self.stopActiveID, self.stopPassiveID = None, None
                self.change_miu = 1

        self.putEvent()

    def onHFBar(self,bar):

        ###################################################################################
        # 只对passiveBar进行处理
        if bar.vtSymbol == self.activeSymbol:
            return

        if len(self.tickBufferDict[self.passiveSymbol])<100:
            return

        # 计算价差       
        midPassive = (self.tickBufferDict[self.passiveSymbol][-1].askPrice1 + self.tickBufferDict[self.passiveSymbol][-1].bidPrice1)/2
        midActive = (self.tickBufferDict[self.activeSymbol][-1].askPrice1 + self.tickBufferDict[self.activeSymbol][-1].bidPrice1)/2
        spread = midActive - midPassive 
        activeAsk1 = self.tickBufferDict[self.activeSymbol][-1].askPrice1
        activeBid1 = self.tickBufferDict[self.activeSymbol][-1].bidPrice1
        passiveAsk1 = self.tickBufferDict[self.passiveSymbol][-1].askPrice1
        passiveBid1 = self.tickBufferDict[self.passiveSymbol][-1].bidPrice1

        if self.change_miu == 1:
            if self.pos == 0 and len(self.limitOrderDict.keys()) == 0:
                # 当前没有持仓也没有未成交挂单
                self.miu_short_list.append(np.mean(self.spreadBuffer[-self.lagtime:]))
                self.miu_long_list.append(np.mean(self.spreadBuffer[-self.lagtime*2:]))
                self.miu_short = self.miu_short_list[-1] 
                self.miu_long = self.miu_long_list[-1]
                # self.run_stat = self.run_test(np.array(self.spreadBuffer[-self.lagtime:]))
                summean = np.mean(self.amDict[self.activeSymbol].close[-1]+self.amDict[self.passiveSymbol].close[-1])/2
                self.gap = max(self.go*summean,2*self.std)
                self.gapadd = 0.002*summean 
                self.spreadBand = 0.0005*summean
                self.spreadcloseold = self.go2*summean
                self.spreadclose = self.go2*summean     
                self.spreadclosenew = -self.gap + 0.003*summean        
                # self.spreadclose = 0
                # 当长期均值和短期均值差异大时更改gap
                if abs(self.miu_long-self.miu_short) > self.gap:
                    self.gap = 2*abs(self.miu_long-self.miu_short)
                    self.writeCtaLog(u'价差变化过快，请谨慎交易')
                # 更改 miu 和 gap 输出记录到日志
                self.writeCtaLog(u'新的miu_short:%s, miu_long:%s, gap:%s, spreadclose:%s'%(self.miu_short,self.miu_long,self.gap,self.spreadclose))
                self.change_miu = 0  
        
        #先撤销掉所有未完成的委托单       
        if len(self.limitOrderDict.keys()) > 0:
            for order in self.limitOrderDict.keys():
                self.cancelOrder(order)
                self.writeCtaLog(u'撤销%s'%(order))
            self.writeCtaLog(u'ontick本轮撤单结束')         
        else:
            pass 
        
        #根据当前spread判断是否下委托单
        if (spread > self.miu_short + self.spreadBand) and len(self.limitOrderDict.keys()) == 0 and abs(self.pos)<self.maxpos and self.stopLost == 0:
            ### 在两个不同的tick位置排单
            for i in [0,self.mintick]:
                orderid1 = self.short(self.activeSymbol,passiveAsk1+self.miu_short+self.gap+abs(self.pos)*self.gapadd/self.posSize+i,
                self.posSize,priceType = PRICETYPE_LIMITPRICE,levelRate = self.levelRate)[0]
                orderid2 = self.buy(self.passiveSymbol,activeBid1-self.miu_short-self.gap-abs(self.pos)*self.gapadd/self.posSize-i,
                self.posSize,priceType = PRICETYPE_LIMITPRICE,levelRate = self.levelRate)[0]
                self.limitOrderDict[orderid1] = {}
                self.writeCtaLog(u'%s, 已写入orderlist'%(orderid1))
                self.limitOrderDict[orderid2] = {}
                self.writeCtaLog(u'%s 已写入orderlist'%(orderid2))

        elif (spread < self.miu_short - self.spreadBand) and len(self.limitOrderDict.keys()) == 0 and abs(self.pos)<self.maxpos and self.stopLost == 0:
            ### 在两个不同的tick位置排单
            for i in [0,self.mintick]:            
                orderid1 = self.buy(self.activeSymbol,passiveBid1+self.miu_short-self.gap-abs(self.pos)*self.gapadd/self.posSize-i,
                self.posSize,priceType = PRICETYPE_LIMITPRICE,levelRate = self.levelRate)[0]
                orderid2 = self.short(self.passiveSymbol,activeAsk1-self.miu_short+self.gap+abs(self.pos)*self.gapadd/self.posSize+i,
                self.posSize,priceType = PRICETYPE_LIMITPRICE,levelRate = self.levelRate)[0]
                self.limitOrderDict[orderid1] = {}
                self.writeCtaLog(u'%s, 已写入orderlist'%(orderid1))
                self.limitOrderDict[orderid2] = {}
                self.writeCtaLog(u'%s 已写入orderlist'%(orderid2))
                                    
        if self.pos > 0 and (datetime.now()-self.opentime).total_seconds()>30 and len(self.closeOrderDict.keys()) == 0 and self.stopLost == 0:
            #正常发平仓单之前先判断是否需要止损
            if midActive - midPassive < self.miu_short - 1.5*self.gap or (datetime.now()-self.opentime).total_seconds()/60>240:
                self.stopLost = 1
                self.sell(self.activeSymbol,self.tickBufferDict[self.activeSymbol],self.pos)
                self.writeCtaLog('进入主动多头被动空头止损逻辑,sad')
            else:
                # 出场时控制因为对手单量过少带来的滑点
                activeTick = self.tickBufferDict[self.activeSymbol][-1]
                volume = activeTick.bidVolume1+activeTick.bidVolume2+activeTick.bidVolume3
                orderid4 = self.cover(self.passiveSymbol,activeBid1-self.miu_short-self.spreadclose,min(abs(self.pos),volume),priceType = PRICETYPE_LIMITPRICE,levelRate = self.levelRate)[0]
                self.limitOrderDict[orderid4] = {}
                self.closeOrderDict[orderid4] = {}
                self.writeCtaLog(u'主动平多仓，被动平空仓委托, %s 主动委托已写入orderlist'%(orderid4))

        if self.pos < 0 and (datetime.now()-self.opentime).total_seconds()>30 and len(self.closeOrderDict.keys()) == 0 and self.stopLost == 0:
            #正常发平仓单之前先判断是否需要止损     
            if midActive - midPassive > self.miu_short + 1.5*self.gap or (datetime.now()-self.opentime).total_seconds()/60>240:
                self.stopLost = 1
                self.writeCtaLog('进入主动多头被动空头止损逻辑,sad')              
            else:
                # 出场时控制因为对手单量过少带来的滑点
                activeTick = self.tickBufferDict[self.activeSymbol][-1]
                volume = activeTick.askVolume1+activeTick.askVolume2+activeTick.askVolume3
                orderid4 = self.sell(self.passiveSymbol,activeAsk1-self.miu_short+self.spreadclose,min(abs(self.pos),volume),priceType = PRICETYPE_LIMITPRICE,levelRate = self.levelRate)[0]
                self.limitOrderDict[orderid4] = {}
                self.closeOrderDict[orderid4] = {}
                self.writeCtaLog(u'主动平空仓，被动平多仓委托, %s 主动委托已写入orderlist'%(orderid4))                   
       


    # ----------------------------------------------------------------------
    def onBar(self, bar):
        """收到Bar推送（必须由用户继承实现）"""
        self.bg5Dict[bar.vtSymbol].updateBar(bar)
        self.amDict[bar.vtSymbol].updateBar(bar)
        self.datetime[bar.vtSymbol] = bar.datetime
        self.reform += 1
       
                
        #每分钟记录输出的spread：
        if self.datetime[self.activeSymbol] == self.datetime[self.passiveSymbol]:
            self.writeCtaLog('on1MinBar, self.spread:%s,self.trade：%s , pos:%s'%(self.amDict[self.activeSymbol].close[-1]-self.amDict[self.passiveSymbol].close[-1],self.trading,self.pos))
            self.spreadBuffer.append(self.amDict[self.activeSymbol].close[-1]-self.amDict[self.passiveSymbol].close[-1])

     
        # 每半小时进行miu_short和miu_long的更换
        if self.reform > 60 and self.datetime[self.activeSymbol] == self.datetime[self.passiveSymbol]:
            spread = np.array(self.spreadBuffer)
            self.miu_short_list.append(np.mean(spread[-self.lagtime:]))
            self.miu_long_list.append(np.mean(spread[-self.lagtime*2:]))
            self.std = np.std(spread)
            self.reform = 1 
            self.change_miu = 1
        
        # 保留未被撤销的orderID进行比对，如果出现orderID重复则调用restinfo的撤单接口
        # if bar.symbol == self.activeSymbol:
            
            # cancelorderlist = []
            # for orderID in self.limitOrderDict.keys():
            #     if orderID in self.lastminOrderDict.keys():
            #         cancelorderlist.append(orderID)
            
            # # self.writeCtaLog(u'CancelOrderDict:%s'cancelorderlist)
            # # print('$$$$$$$$$$$$$$$$$$$$$',cancelorderlist)            
            # if len(cancelorderlist)!=0:
            #     # print('777777777777777777777777 restinfo cancelorder')
            #     # 策略轮询未知订单
            #     if len(cancelorderlist)<5:
            #         self.batchCancelOrder(cancelorderlist)
            #     elif len(cancelorderlist)<10:
            #         self.batchCancelOrder(cancelorderlist[:5])
            #         self.batchCancelOrder(cancelorderlist[6:])
            #     else:
            #         self.batchCancelOrder(cancelorderlist[:5])
            #         self.batchCancelOrder(cancelorderlist[6:min(10,len(cancelorderlist))])
            #         self.writeCtaLog(u'需要撤销的订单过多，请等待下次撤销')
            #     self.writeCtaLog(u'cancel order restinfo')
            # else:
            #     self.writeCtaLog(u'未发现未撤销订单')
            # self.lastminOrderDict = self.lastminOrderDict
            # print('&&&&&&&&&&&&&&&&&&&&',datetime.now().hour)
            
        #     if datetime.now().hour >= 0 and datetime.now().hour <= 6:
        #         # 晚间更改每次下单仓位
        #         self.posSize = 1
        #         self.maxpos = 3
        #     else:
        #         self.posSize = self.posmorning  
        #         self.maxpos = 3*self.posmorning     
        if len(self.spreadBuffer)>2000:
            self.spreadBuffer = self.spreadBuffer[-1500:] 
        self.putEvent()
        
    
    def on5MinBar(self,bar):
        self.am5Dict[bar.vtSymbol].updateBar(bar)
        
        if self.pos != 0:
            # 持仓时间超过1小时，更改出场参数
            if (datetime.now()-self.opentime).total_seconds()/60 > 60:
                self.spreadclose = self.spreadclosenew 
                self.writeCtaLog('持仓超过1小时，更改selfclose参数')
                # self.mail(u'% 持仓超过1小时了'%self.name)
            elif  (datetime.now()-self.opentime).total_seconds()/60 > 120:
                self.miu_short = self.miu_short_list[-1]
                self.writeCtaLog('持仓超过2小时，更改miu_short参数')
                # self.mail(u'% 持仓超过2小时了'%self.name)
        
        self.putEvent()
  
    # ----------------------------------------------------------------------
    def onOrder(self, order):
        """收到委托变化推送（必须由用户继承实现）"""
        #收到撤单成功推送内部维护limitOrderDict和closeOrderList
        # order.status, -1,已撤销 0 未成交， 1 部分成交， 2 全部成交
        # order.orderID
        self.writeCtaLog(u'onorder收到的订单状态, statu:%s, %s,id:%s, List:%s, dealamount:%s'%(order.status, order.rejectedInfo,order.vtOrderID,self.limitOrderDict,order.tradedVolume))
        
        if order.status == STATUS_UNKNOWN:
            content = u'SOS, status, %s, %s, %s, %s'%(order.status, order.vtSymbol,order.orderID,order.rejectedInfo)
            self.mail(content)
  
        if order.vtOrderID in self.limitOrderDict.keys():
            #开仓的已撤销移除limitOrderDict
            #平仓的全部成交和已撤销移除limitOrderDict
            if order.status == STATUS_CANCELLED:
                self.limitOrderDict.pop(order.vtOrderID)
                self.writeCtaLog(u'被撤销的订单 %s 已从limitOrderDict里移除'%order.vtOrderID)

            elif order.status == STATUS_REJECTED:
                self.limitOrderDict.pop(order.vtOrderID)
                self.writeCtaLog(u'被拒绝的订单 %s 已从limitOrderDict里移除'%order.vtOrderID)

            elif order.status == STATUS_PARTTRADED or order.status == STATUS_ALLTRADED:
                if order.vtSymbol == self.passiveSymbol:
                   
                    if order.direction == DIRECTION_LONG and order.offset == OFFSET_OPEN:
                        self.short(self.activeSymbol, self.tickBufferDict[self.activeSymbol][-1].bidPrice1*0.995,order.thisTradedVolume, priceType = PRICETYPE_LIMITPRICE,levelRate = self.levelRate)    
                        self.writeCtaLog(u'被动买开先成交，主动追入卖开:')
                        self.pos -= order.thisTradedVolume

                    elif order.direction == DIRECTION_SHORT and order.offset == OFFSET_OPEN:
                        self.buy(self.activeSymbol, self.tickBufferDict[self.activeSymbol][-1].askPrice1*1.015,order.thisTradedVolume, priceType = PRICETYPE_LIMITPRICE,levelRate = self.levelRate)
                        self.writeCtaLog(u'被动卖开先成交，主动追入买开：')
                        self.pos += order.thisTradedVolume

                    elif order.direction == DIRECTION_LONG and order.offset == OFFSET_CLOSE:
                        self.sell(self.activeSymbol, self.tickBufferDict[self.activeSymbol][-1].bidPrice1*0.995,order.thisTradedVolume, priceType = PRICETYPE_LIMITPRICE,levelRate = self.levelRate)
                        self.writeCtaLog(u'被动买平先成交，主动追入卖平：')
                        self.pos -= order.thisTradedVolume
                        # after offset_close ,check position, if position = 0, update miu_short
                        if self.pos == 0:
                            self.change_miu = 1
                            self.spreadclose = self.spreadcloseold
                            self.writeCtaLog('update miu_short after close, new miu_short:%s'%self.miu_short)

                    elif order.direction == DIRECTION_SHORT and order.offset == OFFSET_CLOSE:
                        self.cover(self.activeSymbol, self.tickBufferDict[self.activeSymbol][-1].askPrice1*1.015,order.thisTradedVolume, priceType = PRICETYPE_LIMITPRICE,levelRate = self.levelRate)
                        self.writeCtaLog(u'被动卖平先成交，主动追入买平：')
                        self.pos += order.thisTradedVolume
                        # after offset_close ,check position, if position = 0, update miu_short
                        if self.pos == 0:
                            self.change_miu = 1
                            self.spreadclose = self.spreadcloseold
                            self.writeCtaLog('update miu_short after close, new miu_short:%s'%self.miu_short)
                
                elif order.vtSymbol == self.activeSymbol:
                   
                    if order.direction == DIRECTION_LONG and order.offset == OFFSET_OPEN:
                        self.short(self.passiveSymbol, self.tickBufferDict[self.passiveSymbol][-1].bidPrice1*0.995,order.thisTradedVolume, 
                                     priceType = PRICETYPE_LIMITPRICE,levelRate = self.levelRate)
                        self.writeCtaLog(u'主动买开先成交，被动追入卖开: ')
                        self.pos += order.thisTradedVolume
 
                    elif order.direction == DIRECTION_SHORT and order.offset == OFFSET_OPEN:
                        self.buy(self.passiveSymbol, self.tickBufferDict[self.passiveSymbol][-1].askPrice1*1.015,order.thisTradedVolume, 
                                 priceType = PRICETYPE_LIMITPRICE,levelRate = self.levelRate)
                        self.writeCtaLog(u'主动卖开先成交，被动追入买开：')  
                        self.pos -= order.thisTradedVolume              

            if order.status == STATUS_ALLTRADED:
                self.limitOrderDict.pop(order.vtOrderID)
                self.writeCtaLog('已成交的订单 %s 已从limitOrderDict里移除'%order.vtOrderID)
            elif  order.status == STATUS_UNKNOWN:
                self.limitOrderDict.pop(order.vtOrderID) 

        else:
            # 变动的订单是市价追单
            if order.status == STATUS_REJECTED:
                ####市价追单再发一遍
                if order.direction == DIRECTION_LONG and order.offset == OFFSET_OPEN:
                    self.buy(order.vtSymbol,order.price,order.totalVolume,priceType = PRICETYPE_MARKETPRICE)
                elif order.direction == DIRECTION_LONG and order.offset == OFFSET_CLOSE:
                    self.cover(order.vtSymbol,order.price,order.totalVolume,priceType = PRICETYPE_MARKETPRICE)
                elif order.direction == DIRECTION_SHORT and order.offset == OFFSET_OPEN:
                    self.short(order.vtSymbol,order.price,order.totalVolume,priceType = PRICETYPE_MARKETPRICE)
                elif order.direction == DIRECTION_SHORT and order.offset == OFFSET_CLOSE:
                    self.sell(order.vtSymbol,order.price,order.totalVolume,priceType = PRICETYPE_MARKETPRICE)
                self.writeCtaLog(u'拒单重新发市价单：%s,%s,%s,%s'%(order.vtSymbol,order.direction,order.offset,order.totalVolume))

        if order.thisTradedVolume != 0:
            content = u'symbol:%s, direction:%s, offset:%s,price:%s,amount:%s'%(order.vtSymbol,order.direction,order.offset,order.price,order.thisTradedVolume)
            self.mail(content)

        if order.vtOrderID in self.closeOrderDict.keys():
            if order.status == STATUS_ALLTRADED or order.status == STATUS_CANCELLED or order.status == STATUS_REJECTED:
                self.closeOrderDict.pop(order.vtOrderID)

        if self.stopLost == 1:
            if order.vtOrderID == self.stopActiveID and order.status == STATUS_ALLTRADED:
                self.stopActiveID = 'Done'
            elif order.vtOrderID == self.stopPassiveID and order.status == STATUS_ALLTRADED:
                self.stopPassiveID = 'Done'
            elif order.vtOrderID == self.stopActiveID and order.status == STATUS_REJECTED:
                #### 拒单重发市价单
                if order.direction == DIRECTION_LONG:
                    self.stopActiveID = self.cover(self.activeSymbol,order.price,abs(pos),priceType=PRICETYPE_MARKETPRICE)[0]
                else:
                    self.stopActiveID = self.sell(self.activeSymbol,order.price,abs(pos),priceType=PRICETYPE_MARKETPRICE)[0]
            elif order.vtOrderID == self.stopPassiveID and order.status == STATUS_REJECTED:
                #### 拒单重发市价单
                if order.direction == DIRECTION_LONG:
                    self.stopPassiveID = self.cover(self.passiveSymbol,order.price,abs(pos),priceType=PRICETYPE_MARKETPRICE)[0]
                else:
                    self.stopPassiveID = self.sell(self.passiveSymbol,order.price,abs(pos),priceType=PRICETYPE_MARKETPRICE)[0]
                        
        self.putEvent()


    # ----------------------------------------------------------------------
    def onTrade(self, trade):
        # 下单后报单
        # 根据成交的单修改limitOrderDict和CloseOrderLis写在了onOrder里
        self.writeCtaLog(u'%s,%s成交了,方向：%s,  开平：%s'%(trade.orderID, trade.vtSymbol, trade.direction, trade.offset))
        if trade.offset == OFFSET_OPEN:
            self.opentime = datetime.now()
            self.writeCtaLog(u'priceList:%s'%self.lastPriceDict[trade.vtSymbol][-50:])
            self.writeCtaLog(u'askbidvolumeList:%s'%self.askbidVolumeDict[trade.vtSymbol][-50:])
            # self.writeCtaLog(u'lastTick:%s'%self.tickBufferDict[trade.vtSymbol][-1])
            self.lastPriceDict[trade.vtSymbol] = []
            self.askbidVolumeDict[trade.vtSymbol] = []
        self.putEvent()

    # ----------------------------------------------------------------------
    def onStopOrder(self, so):
        """停止单推送"""
        pass
