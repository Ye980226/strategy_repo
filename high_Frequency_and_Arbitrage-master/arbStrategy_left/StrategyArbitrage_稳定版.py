# encoding: UTF-8

"""
套利策略
策略版本 1.3
vnpy版本 1.1.16-patch02

# 先进passive后进active
# 挂撤单逻辑写入tick, 按每20个tick挂撤单
# 分多条线进出场，千分之7,8,9设立阈值，止盈按千分之0,-1,-2
# 每过一段时间 reform 调整一次参数
# 使用过去 forming 时间长度的数据估计参数
# floor 开仓挂单阈值，相当于之前的gap
# rev_floor 平仓挂单阈值，相当于之前的spreadclose, 负号表示和floor所处的价差同方向
# 2019年1月12日 19:31:49
# 撤单时增加限流
# 2019年1月17日 11:18:35
# 合并订单
# 2019年1月18日 13:58:10
# 止盈随时间变化逐渐减小
# 2019年1月29日 17:17:30
"""

from vnpy.trader.vtConstant import *
# EMPTY_STRING, DIRECTION_LONG, DIRECTION_SHORT,OFFSET_OPEN, OFFSET_CLOSE,
# STATUS_CANCELLED,STATUS_NOTTRADED,STATUS_PARTTRADED,STATUS_ALLTRADED
from vnpy.trader.app.ctaStrategy.ctaTemplate import (CtaTemplate,
                                                     BarGenerator,
                                                     ArrayManager)
from collections import defaultdict
import numpy as np
import pandas as pd
import time
from datetime import datetime, timedelta

########################################################################
class ArbitrageStrategy(CtaTemplate):
    """配对交易策略"""
    className = 'ArbitrageStrategy_update'
    author = 'zongzong'
    version = '1.1.16'
    
    # 策略交易标的
    #symbolList = []                 # 初始化为空
    activeSymbol = EMPTY_STRING     # 主动品种
    passiveSymbol = EMPTY_STRING    # 被动品种
    
    # 参数列表，保存了参数的名称
    paramList = ['name',
                 'className',
                 'author']

    # 变量列表，保存了变量的名称
    varList = ['inited',
               'trading',
               'posDict']

    # 同步列表，保存了需要保存到数据库的变量名称
    # syncList = ['posDict',
    #             'eveningDict']

    # ----------------------------------------------------------------------
    def __init__(self, ctaEngine, setting):
        """Constructor"""
        super(ArbitrageStrategy, self).__init__(ctaEngine, setting)
        
        self.marketRatio = setting['marketRatio']  # 按照最高价和最低价加减x个最小价格变动单位设置市价追单价格
        self.contractMinitick = setting['contractMintick']  # 所交易合约的最小价格变动单位
        self.stopLossMarginCall = setting['stopLossMarginCall']  # 价格止损预警线
        self.slipper = setting['slipper']  # 在已有的价差阈值上增加slipper乘以minitick控制成交滑点
        self.posSize_day = setting['posSize_day']  # posSize表示每次下单的量
        self.posSize_night = setting['posSize_night']
        self.posSize = self.posSize_day
        self.forming = setting['forming']  # 用过去多长时间（分钟）的数据估计均值
        self.startSS = setting['startSS']  # 开仓后多少秒开始进入止损逻辑
        self.startTT = setting['startTT']  # 开仓后多少秒开始进入止盈逻辑
        self.startTS = setting['startTS']  # 开仓后多少秒开始进入时间止损逻辑
        self.floors = setting['floors']  #一个list储存进场阈值，千分之x
        self.rever_floors = setting['rever_floors']  #一个list存储出场阈值，千分之x
        self.stopLoss = setting['stopLoss_Ratio']  #相对于floor值设置的止损线，x倍的floor
        self.floor_add = 0  #当观测到远期均值和近期均值差异大时设置大于0，进一步增加进场阈值，其它情况为0
        self.maxPos_day = setting['maxPos_day'] #每一档最多持仓量的一半
        self.maxPos_night = setting['maxPos_night']
        self.maxPos = self.maxPos_day
        self.spreadBand = setting['spreadBand'] 
        
        

    def registerTimer500Ms(self):
        import threading
        from vnpy.event import Event
        
        EVENT_TIMER_500_MS = "timer_500_ms"
        self.ctaEngine.eventEngine.register(EVENT_TIMER_500_MS, self.onTimer500Ms)
        def timer(eventEngine, interval=500):
            while True:
                eventEngine.put(Event(type_=EVENT_TIMER_500_MS))
                time.sleep(interval / 1000)
        thread = threading.Thread(target=timer, args=(self.ctaEngine.eventEngine, ))
        thread.daemon = True
        thread.start()


    def registerTimer1000Ms(self):
        import threading
        from vnpy.event import Event
        
        EVENT_TIMER_1000_MS = "timer_1000_ms"
        self.ctaEngine.eventEngine.register(EVENT_TIMER_1000_MS, self.onTimer1000Ms)
        def timer(eventEngine, interval=1000):
            while True:
                eventEngine.put(Event(type_=EVENT_TIMER_1000_MS))
                time.sleep(interval / 1000)
        thread = threading.Thread(target=timer, args=(self.ctaEngine.eventEngine, ))
        thread.daemon = True
        thread.start()



    # ----------------------------------------------------------------------
    def onInit(self):
        """初始化策略（必须由用户继承实现）"""
        self.writeCtaLog(u'%s策略初始化' % self.name)
        self.activeSymbol = self.symbolList[0]
        self.passiveSymbol = self.symbolList[1]
        # 生成1分钟bar推送
        self.generateBarDict(self.onBar,size=800)
        # 生成1s高频bar，不用于updateBar，仅用于2s一次触发逻辑
        # self.generateHFBar(1,size=100)  
        # 记录本次成交的成交价
        self.dealPriceDict = {}

        engine = self.getEngineType()
        # 初始化一些用于数据的列表和计数器
        self.barSpreadBuffer = []
        self.activeDatetime = datetime.now()
        self.passiveDatetime = datetime.now()

        ###### 缓存被动的volume
        self.passiveAskVolume1 = np.zeros(30)
        self.passiveBidVolume1 = np.zeros(30) 
        ###### 缓存主动的volume
        self.activeAskVolume1 = np.zeros(30)
        self.activeBidVolume1 = np.zeros(30)

        ###### 缓存上一次的市价追入发单时间
        self.lastMarketOrderTime = datetime.now()

        # 回测读取数据
        if engine == 'trading':
            ### 实盘从交易所读取数据
            activekline = self.loadHistoryBar(self.activeSymbol, '1min', 800)
            passivekline = self.loadHistoryBar(self.passiveSymbol,'1min',800)
            ### 将读取的数据填入amDict
            for activebar,passivebar in zip(activekline,passivekline):
                print(activebar.datetime,activebar.close,passivebar.datetime,passivebar.close)
                self.amDict[self.activeSymbol].updateBar(activebar)
                self.amDict[self.passiveSymbol].updateBar(passivebar)
                self.barSpreadBuffer.append(activebar.close-passivebar.close)

            self.writeCtaLog('请确认时间是否一致:active:%s,passive%s'%(activebar.datetime,passivebar.datetime))

            ## 只有当价差至少到达gap_base才开始发开仓单
            self.summean = np.mean(self.amDict[self.activeSymbol].close[-1] + self.amDict[self.passiveSymbol].close[-1])/2
            self.gap_base = 0.001*self.summean
            self.miu=np.mean(np.array(self.barSpreadBuffer[-self.forming:]))
            self.miu_long=np.mean(np.array(self.barSpreadBuffer[-self.forming*3:]))
               
            if abs(self.miu_long-self.miu)/self.summean > self.floors[0]:
                self.floor_add = abs(self.miu_long-self.miu)/self.summean
            else:
                self.floor_add = 0           
            self.writeCtaLog('初始化参数成功, miu:%s, floor_add:%s'%(self.miu, self.floor_add))
        
        else:
            self.initBacktesingData()
    
        ## 生成订单字典，通过字典管理订单
        self.floorDict = {floor:{
                                ### 以下用于记录每次成交价
                                'passiveBuyPrice':[],  
                                'passiveShortPrice':[],
                                'passiveCoverPrice':[],
                                'passiveSellPrice':[],
                                'activeBuyPrice':[],
                                'activeShortPrice':[],
                                'activeCoverPrice':[],
                                'activeSellPrice':[],   
                                ### 以下用于记录每次成交量
                                'passiveBuyVolume':[],  
                                'passiveShortVolume':[],
                                'passiveCoverVolume':[],
                                'passiveSellVolume':[],
                                'activeBuyVolume':[],
                                'activeShortVolume':[],
                                'activeCoverVolume':[],
                                'activeSellVolume':[],                                 

                                'miu_longActive':self.miu,   # 记录均值
                                'miu_shortActive':self.miu,  # 记录均值
                                'floor_add':self.floor_add,  # 价格异常时增加值
                                'floor':floor,    # 对应的开仓阈值
                                'rev_floor':rever_floor,  # 对应的平仓阈值
                                # 'gap_base':self.gap_base,  # 对应的开始挂单阈值
                                'Time':datetime.now(),   # 之后用于存储开仓时间
                                'longActiveOpen':0,
                                'shortActiveOpen':0,
                                'longActivePos':0,    # 主动多头被动空头的持仓
                                'shortActivePos':0,  #主动空头被动多头的持仓  
                                'longActiveClose':0,
                                'shortActiveClose':0,
                                'summean':self.summean
                                } for floor,rever_floor in zip(self.floors,self.rever_floors)}
        
        ### 订单对应floor的映射
        self.passiveBuyMap = {}
        self.passiveShortMap = {}
        self.passiveSellMap = {}
        self.passiveCoverMap = {}
        #############
        self.activeBuyMap = {}
        self.activeShortMap = {} 
        #############
        self.cancelOrderDict = {}  
        self.marketOrderDict = {}    
        #######    市价追单合并订单  #############
        self.mergeOrderDict = {
            sym:{
                'buy':0,
                'short':0,
                'sell':0,
                'cover':0
            } for sym in self.symbolList
        }
        print(self.mergeOrderDict)
        self.mergeFloorDict = {
            sym:{
                floor:{
                    'buy':0,
                    'short':0,
                    'sell':0,
                    'cover':0                   
                } for floor in self.floors
            } for sym in self.symbolList
        }

        
        # 创建tick数据缓存容器
        self.tickBufferDict = {
            sym: []
            for sym in self.symbolList
        } 
        self.registerTimer500Ms()
        self.registerTimer1000Ms()
        self.putEvent()

    # ----------------------------------------------------------------------
    def onStart(self):
        """启动策略（必须由用户继承实现）"""
        self.writeCtaLog(u'%s策略启动' % self.name)
        self.putEvent()

    # ----------------------------------------------------------------------
    def onStop(self):
        """停止策略（必须由用户继承实现）"""
        self.writeCtaLog(u'%s策略停止' % self.name)
        self.putEvent()

    # ----------------------------------------------------------------------
    def onTick(self, tick):
        """收到行情TICK推送"""

        ### 生成对应的bar并推送
        # self.writeCtaLog('进入onTick时间:%s'%datetime.now())
        self.tickBufferDict[tick.vtSymbol].append(tick)  
        self.bgDict[tick.vtSymbol].updateTick(tick)  
        # self.writeCtaLog('离开onTick时间:%s'%datetime.now())
        
        ### 更新内部缓存的对手盘挂单数量 ####
        if tick.vtSymbol == self.passiveSymbol and tick.volumeChange == 0:
            self.passiveAskVolume1[:-1] = self.passiveAskVolume1[1:]
            self.passiveAskVolume1[-1] = tick.askVolume1
            self.passiveBidVolume1[:-1] = self.passiveBidVolume1[1:]
            self.passiveBidVolume1[-1] = tick.bidVolume1
        elif tick.vtSymbol == self.activeSymbol and tick.volumeChange == 0:
            self.activeAskVolume1[:-1] = self.activeAskVolume1[1:]
            self.activeAskVolume1[-1] = tick.askVolume1
            self.activeBidVolume1[:-1] = self.activeBidVolume1[1:]
            self.activeBidVolume1[-1] = tick.bidVolume1        
        
        
        self.putEvent()
    
    # ------------------------------------------------------------------------------
    def dealPrice(self,order):
        
        price = order.price_avg
        # if order.vtOrderID not in self.dealPriceDict:
        #     ### 第一次收到的订单
        #     if order.status == STATUS_PARTTRADED:
        #         price = order.price_avg
        #         self.dealPriceDict[order.vtOrderID]=order.price_avg*order.tradedVolume
        #     elif order.status == STATUS_ALLTRADED:
        #         price = order.price_avg
        # else:
        #     ### 第二次到达的订单计算本次成交量和本次成交价
        #     if order.status == STATUS_PARTTRADED:
        #         price = (order.price_avg*order.tradedVolume-self.dealPriceDict[order.vtOrderID])/order.thisTradedVolume
        #         self.dealPriceDict[order.vtOrderID]=order.price_avg*order.tradedVolume
        #     elif order.status == STATUS_ALLTRADED:
        #         price = (order.price_avg*order.tradedVolume-self.dealPriceDict[order.vtOrderID])/order.thisTradedVolume
        #         del self.dealPriceDict[order.vtOrderID]
        #     elif order.status == STATUS_CANCELLED:
        #         del self.dealPriceDict[order.vtOrderID]

        return price                
                
    
    # --------------------------------------------------------------------------------
    def followOrder(self, symbol, followType, volume):
        # 市价追单
        if followType == 'buy':
            orderid = self.buy(symbol,self.tickBufferDict[symbol][-1].upperLimit-self.marketRatio*self.contractMinitick,volume)
        elif followType == 'short':
            orderid = self.short(symbol, self.tickBufferDict[symbol][-1].lowerLimit+self.marketRatio*self.contractMinitick,volume)
        elif followType == 'sell':
            orderid = self.sell(symbol,self.tickBufferDict[symbol][-1].lowerLimit+self.marketRatio*self.contractMinitick,volume)
        elif followType == 'cover':
            orderid = self.cover(symbol,self.tickBufferDict[symbol][-1].upperLimit-self.marketRatio*self.contractMinitick,volume)
        return orderid[0]
    

    # ------------------------------------------------------------------------------
    def limitOrderOpen(self,order,mapDict,
                posOpen='shortActiveOpen',posPos='shortActivePos',posClose='shortActiveClose',
                next_symbol=activeSymbol,next_type='short'):
        
        thisPrice = self.dealPrice(order)  #成交时为本次成交价，其它情况为None

        ### 对限价开仓订单进行操作
        level = mapDict[order.vtOrderID]
        if order.status == STATUS_CANCELLED:
            ## 撤销订单注意维护字典
            self.floorDict[level][posOpen] -= order.totalVolume - order.tradedVolume 
            del mapDict[order.vtOrderID]
            del self.cancelOrderDict[order.vtOrderID]
        
        elif order.status == STATUS_REJECTED:
            ##  开仓单被拒单等同撤销处理
            self.floorDict[level][posOpen] -= order.totalVolume - order.tradedVolume 
            del mapDict[order.vtOrderID]
            del self.cancelOrderDict[order.vtOrderID]             
        
        elif order.status == STATUS_PARTTRADED or order.status == STATUS_ALLTRADED:
            self.floorDict[level][posOpen] -= order.thisTradedVolume
            self.floorDict[level][posPos] += order.thisTradedVolume  
            self.floorDict[level]['Time'] = datetime.now()
            ## 市价追另一边
            if next_type == 'short':
                self.writeCtaLog('品种:%s buy买开先成交，另一个品种市价追入, floor:%s,%s单向持仓：%s'%(order.vtSymbol,
                                level,posPos,self.floorDict[level][posPos])) 
                self.mergeOrderDict[next_symbol]['short'] += order.thisTradedVolume
                self.mergeFloorDict[next_symbol][level]['short'] += order.thisTradedVolume
                
                self.nowDo(datetime.now()) ## 判断是否发市价追单

                # order1 = self.followOrder(next_symbol,'short',order.thisTradedVolume)
                # self.marketOrderDict[order1] = {
                #     'Time':datetime.now(),
                #     'type':'short',
                #     'symbol':next_symbol,
                #     'volume':order.thisTradedVolume,
                #     'status':'wait',
                #     'floor':level,
                # }

            elif next_type == 'buy':
                self.writeCtaLog('品种:%s short卖开先成交，另一个品种市价追入，floor:%s,%s单向持仓：%s'%(order.vtSymbol,
                                level,posPos,self.floorDict[level][posPos]))
                self.mergeOrderDict[next_symbol]['buy'] += order.thisTradedVolume
                self.mergeFloorDict[next_symbol][level]['buy'] += order.thisTradedVolume
                
                self.nowDo(datetime.now()) ## 判断是否发市价追单

                # order1 = self.followOrder(next_symbol,'buy',order.thisTradedVolume)
                # self.marketOrderDict[order1] = {
                #     'Time':datetime.now(),
                #     'type':'buy',
                #     'symbol':next_symbol,
                #     'volume':order.thisTradedVolume,
                #     'status':'wait',
                #     'floor':level
                # }                
                
            ## 成交后记录价格
            if order.vtSymbol == self.passiveSymbol and order.direction==DIRECTION_LONG: #被动买开
                self.floorDict[level]['passiveBuyPrice'].append(thisPrice)
                self.floorDict[level]['passiveBuyVolume'].append(order.thisTradedVolume)
            elif order.vtSymbol == self.passiveSymbol and order.direction==DIRECTION_SHORT: #被动卖开
                self.floorDict[level]['passiveShortPrice'].append(thisPrice)
                self.floorDict[level]['passiveShortVolume'].append(order.thisTradedVolume)
            elif order.vtSymbol == self.activeSymbol and order.direction==DIRECTION_LONG: #主动买开
                self.floorDict[level]['activeBuyPrice'].append(thisPrice)
                self.floorDict[level]['activeBuyVolume'].append(order.thisTradedVolume)
            elif order.vtSymbol == self.activeSymbol and order.direction==DIRECTION_SHORT: #主动卖开
                self.floorDict[level]['activeShortPrice'].append(thisPrice)
                self.floorDict[level]['activeShortVolume'].append(order.thisTradedVolume)
            

            if order.status == STATUS_ALLTRADED:                  
                del mapDict[order.vtOrderID]
                del self.cancelOrderDict[order.vtOrderID]

    # ----------------------------------------------------------------------------
    def limitCloseOrder(self,order,mapDict,
                posOpen='shortActiveOpen',posPos='shortActivePos',posClose='shortActiveClose',
                next_symbol=activeSymbol,next_type='cover'):
        
        thisPrice = self.dealPrice(order)

        ## 对限价平仓订单进行操作   
        level = mapDict[order.vtOrderID]
        if order.status == STATUS_CANCELLED:
            ## 撤销订单注意维护字典
            self.floorDict[level][posClose] -= order.totalVolume - order.tradedVolume 
            del mapDict[order.vtOrderID]
            del self.cancelOrderDict[order.vtOrderID]
        
        elif order.status == STATUS_REJECTED:
            ##  开仓单被拒单等同撤销处理
            self.floorDict[level][posClose] -= order.totalVolume - order.tradedVolume 
            del mapDict[order.vtOrderID]
            del self.cancelOrderDict[order.vtOrderID] 

        elif order.status == STATUS_PARTTRADED or order.status == STATUS_ALLTRADED:
            self.floorDict[level][posClose] -= order.thisTradedVolume
            self.floorDict[level][posPos] -= order.thisTradedVolume  # 是否考虑在收到另一个品种的成交回报再修改posPos
            ## 市价追主动
            self.writeCtaLog('floor:%s被动平仓先出场成交，主动追入平仓，方向:%s'%(level,posPos))

            self.mergeOrderDict[next_symbol][next_type] += order.thisTradedVolume
            self.mergeFloorDict[next_symbol][level][next_type] += order.thisTradedVolume
            
            self.nowDo(datetime.now()) ## 判断是否发市价追单

            # order1 = self.followOrder(next_symbol,next_type,order.thisTradedVolume)
            # self.marketOrderDict[order1] = {
            #     'Time':datetime.now(),
            #     'type':next_type,
            #     'symbol':next_symbol,
            #     'volume':order.thisTradedVolume,
            #     'status':'wait',
            #     'floor':level
            # }
            if order.status == STATUS_ALLTRADED:
                ## 全部成交记录价格并删除字典
                if order.vtSymbol == self.passiveSymbol and order.direction==DIRECTION_LONG: #被动买平
                    self.floorDict[level]['passiveCoverPrice'].append(thisPrice)
                    self.floorDict[level]['passiveCoverVolume'].append(order.thisTradedVolume)
                elif order.vtSymbol == self.passiveSymbol and order.direction==DIRECTION_SHORT: #被动卖平
                    self.floorDict[level]['passiveSellPrice'].append(thisPrice)
                    self.floorDict[level]['passiveSellVolume'].append(order.thisTradedVolume)
                elif order.vtSymbol == self.activeSymbol and order.direction==DIRECTION_LONG: #主动买平
                    self.floorDict[level]['activeCoverPrice'].append(thisPrice)
                    self.floorDict[level]['activeCoverVolume'].append(order.thisTradedVolume)
                elif order.vtSymbol == self.activeSymbol and order.direction==DIRECTION_SHORT: #主动卖平
                    self.floorDict[level]['activeSellPrice'].append(thisPrice)
                    self.floorDict[level]['activeSellVolume'].append(order.thisTradedVolume)
                del mapDict[order.vtOrderID]
                del self.cancelOrderDict[order.vtOrderID]
   

    # ---------2019年1月11日 19:32:32-----------------------------------------------
    def onOrder(self, order):
        
        ### 
        self.writeCtaLog('进入onOrder时间：%s'%datetime.now())
        self.writeCtaLog('收到订单回报，orderDatetime:%s,localId:%s, price:%s, symbol:%s, direction：%s, offset:%s, status:%s'%(order.orderDatetime,
                        order.vtOrderID, order.price,order.vtSymbol,order.direction,order.offset,order.status))
        
        ### 根据订单状态修改字典，进行操作
        if order.offset == OFFSET_OPEN:
            if order.vtOrderID in self.passiveBuyMap:
                self.limitOrderOpen(order,self.passiveBuyMap,
                'shortActiveOpen','shortActivePos','shortActiveClose',
                self.activeSymbol,'short')
            
            elif order.vtOrderID in self.passiveShortMap:
                self.limitOrderOpen(order,self.passiveShortMap,
                'longActiveOpen','longActivePos','longActiveClose',
                self.activeSymbol,'buy')

            elif order.vtOrderID in self.activeBuyMap:
                self.limitOrderOpen(order,self.activeBuyMap,
                'longActiveOpen','longActivePos','longActveClose',
                self.passiveSymbol,'short')

            elif order.vtOrderID in self.activeShortMap:
                self.limitOrderOpen(order,self.activeShortMap,
                'shortActiveOpen','shortActivePos','shortActiveClose',
                self.passiveSymbol,'buy')

        else:
            if order.vtOrderID in self.passiveSellMap:
                self.limitCloseOrder(order,self.passiveSellMap,
                'shortActiveOpen','shortActivePos','shortActiveClose',
                self.activeSymbol,'cover')
            
            elif order.vtOrderID in self.passiveCoverMap:
                self.limitCloseOrder(order,self.passiveCoverMap,
                'longActiveOpen','longActivePos','longActiveClose',
                self.activeSymbol,'sell')

        ##### 对于市价单使用循环追单的方法 ############
        if order.vtOrderID in self.marketOrderDict:
            if order.status == STATUS_CANCELLED:
                ### 收到撤单立刻按照未成交量重发
                if order.totalVolume-order.tradedVolume!=0:
                    orderType = self.marketOrderDict[order.vtOrderID]['type']
                    orderid5 = self.followOrder(order.vtSymbol, orderType, order.totalVolume-order.tradedVolume)
                    self.marketOrderDict[orderid5] = {
                        'Time':datetime.now(),
                        'type':orderType,
                        'symbol':order.vtSymbol,
                        'volume':order.totalVolume-order.tradedVolume,
                        'status':'wait',
                        'floor':self.marketOrderDict[order.vtOrderID]['floor']                        
                    }
                    ## 已撤销删除字典
                    del self.marketOrderDict[order.vtOrderID]
            elif order.status == STATUS_REJECTED:
                ### 收到拒单先记录，等下一次遍历字典时再发
                self.marketOrderDict[order.vtOrderID]['status'] = 'reject'
            elif order.status == STATUS_PARTTRADED:
                self.marketOrderDict[order.vtOrderID]['volume'] -= order.thisTradedVolume
            elif order.status == STATUS_ALLTRADED:
                
                """
                    for floor in self.mergeFloorDict[sym]:
                        tempDict[floor] = self.mergeFloorDict[sym][floor][key]
                        self.mergeFloorDict[sym][floor][key] = 0 ## 维护字典
                    self.marketOrderDict[orderid1] = {
                        'Time':datetime.now(),
                        'type':key,
                        'symbol':sym,
                        'volume':values,
                        'status':'wait',
                        'floor': {
                            0.005:10，
                            0.007:15
                            } ...
                        }  ... 
                    }
                """
                Type = self.marketOrderDict[order.vtOrderID]['type']

                for level in self.marketOrderDict[order.vtOrderID]['floor']:
                    if order.vtSymbol == self.passiveSymbol:
                        if Type == 'short':
                            self.floorDict[level]['passiveShortPrice'].append(order.price_avg)
                            self.floorDict[level]['passiveShortVolume'].append(self.marketOrderDict[order.vtOrderID]['floor'][level])
                        elif Type == 'buy':
                            self.floorDict[level]['passiveBuyPrice'].append(order.price_avg)
                            self.floorDict[level]['passiveBuyPrice'].append(self.marketOrderDict[order.vtOrderID]['floor'][level])
                        elif Type == 'cover':
                            self.floorDict[level]['passiveCoverPrice'].append(order.price_avg)
                            self.floorDict[level]['passiveCoverVolume'].append(self.marketOrderDict[order.vtOrderID]['floor'][level])
                        elif Type == 'sell':
                            self.floorDict[level]['passiveSellPrice'].append(order.price_avg)
                            self.floorDict[level]['passiveSellVolume'].append(self.marketOrderDict[order.vtOrderID]['floor'][level])
                    else:
                        if Type == 'short':
                            self.floorDict[level]['activeShortPrice'].append(order.price_avg)
                            self.floorDict[level]['activeShortVolume'].append(self.marketOrderDict[order.vtOrderID]['floor'][level])
                        elif Type == 'buy':
                            self.floorDict[level]['activeBuyPrice'].append(order.price_avg)
                            self.floorDict[level]['activeBuyPrice'].append(self.marketOrderDict[order.vtOrderID]['floor'][level])
                        elif Type == 'cover':
                            self.floorDict[level]['activeCoverPrice'].append(order.price_avg)
                            self.floorDict[level]['activeCoverVolume'].append(self.marketOrderDict[order.vtOrderID]['floor'][level])
                        elif Type == 'sell':
                            self.floorDict[level]['activeSellPrice'].append(order.price_avg)
                            self.floorDict[level]['activeSellVolume'].append(self.marketOrderDict[order.vtOrderID]['floor'][level])                  
                            
                    if order.vtSymbol == self.activeSymbol and order.offset == OFFSET_CLOSE:
                        ########################### 输出本次成交结果 ##############################
                        if self.floorDict[level]['longActivePos'] == 0 and order.direction==DIRECTION_SHORT:
                            oneDict = self.floorDict[level]
                            ret = np.mean(oneDict['activeSellPrice'])-np.mean(oneDict['activeBuyPrice'])+np.mean(oneDict['passiveShortPrice'])-np.mean(oneDict['passiveCoverPrice'])
                            self.writeCtaLog('floor:%s做多价差(longActiveShortPassive)组合已经平仓离场，本次1个eos面值的合约净赚_%s_美金(仅在posSize=1成立)'%(level,ret))
                            self.writeCtaLog(str(oneDict))
                            self.floorDict[level]['activeSellPrice'] = []
                            self.floorDict[level]['activeBuyPrice'] = []
                            self.floorDict[level]['passiveShortPrice'] = []
                            self.floorDict[level]['passiveCoverPrice'] = []
                            
                            self.floorDict[level]['activeSellVolume'] = []
                            self.floorDict[level]['activeBuyVolume'] = []
                            self.floorDict[level]['passiveShortVolume'] = []
                            self.floorDict[level]['passiveCoverVolume'] = []
                        
                        elif self.floorDict[level]['shortActivePos'] == 0 and order.direction==DIRECTION_LONG:
                            oneDict = self.floorDict[level]
                            ret = np.mean(oneDict['activeShortPrice'])-np.mean(oneDict['activeCoverPrice'])+np.mean(oneDict['passiveSellPrice'])-np.mean(oneDict['passiveBuyPrice'])
                            self.writeCtaLog('floor:%s做空价差(shortActiveLongPassive)组合已经平仓离场，本次1个eos面值的合约净赚_%s_美金(仅在posSize=1成立)'%(level,ret))
                            self.writeCtaLog(str(oneDict))
                            self.floorDict[level]['activeShortPrice'] = []
                            self.floorDict[level]['activeCoverPrice'] = []
                            self.floorDict[level]['passivBuyPrice'] = []
                            self.floorDict[level]['passiveSellPrice'] = []                

                            self.floorDict[level]['activeShortVolume'] = []
                            self.floorDict[level]['activeCoverVolume'] = []
                            self.floorDict[level]['passivBuyVolume'] = []
                            self.floorDict[level]['passiveSellVolume'] = [] 

                del self.marketOrderDict[order.vtOrderID]


    # --------------------------------------------------------------------------
    """
        #######    市价追单合并订单  #############
        self.mergeOrderDict = {
            sym:{
                'buy':0,
                'short':0,
                'sell':0,
                'cover':0
            } for sym in self.symbolList
        }
        self.mergeFloorDict = {
            sym:{
                floor:{
                    'buy':0,
                    'short':0,
                    'sell':0,
                    'cover':0                   
                } for floor in self.floors
            } for sym in self.symbolList
        } 
    """
    
    def nowDo(self,time):
        ### 查询mergeDict里面的数量并发单
        if (time-self.lastMarketOrderTime).total_seconds()>0.4:
            for sym in self.mergeOrderDict:
                for key,values in self.mergeOrderDict[sym].items(): # key:buy, value:volume
                    if values != 0:
                        orderid1 = self.followOrder(sym, key, values)
                        self.lastMarketOrderTime = datetime.now()
                        
                        ### 生成一个临时字典存储所有floor的key=buy，short，cover，sell的信息
                        tempDict = {}

                        for floor in self.mergeFloorDict[sym]:
                            if self.mergeFloorDict[sym][floor][key] != 0:
                                tempDict[floor] = self.mergeFloorDict[sym][floor][key]
                                self.mergeFloorDict[sym][floor][key] = 0 ## 维护字典
                                        
                        self.marketOrderDict[orderid1] = {
                            'Time':datetime.now(),
                            'type':key,
                            'symbol':sym,
                            'volume':values,
                            'status':'wait',
                            'floor': tempDict      
                        }
                        self.writeCtaLog('合并订单发送，合并量：%s'%(values))
                        self.mergeOrderDict[sym][key] = 0  #发完单后将改档位的待发单量记为0        


    def onTimer500Ms(self, event):
        ### 固定一段时间触发一次，触发nowDo
        self.writeCtaLog('Timer localTime:%s'%datetime.now())
        self.nowDo(datetime.now())
        pass
    
    
    # --------------------------------------------------------------------------
    def onTimer1000Ms(self,event):
        """每隔1s触发一次"""
        ### 保证有数据才进入下一步
        if not self.tickBufferDict[self.activeSymbol]:
            return 
        if not self.tickBufferDict[self.passiveSymbol]:
            return
        
        ### 计算价差
        # 计算价差       
        midPassive = (self.tickBufferDict[self.passiveSymbol][-1].askPrice1 + self.tickBufferDict[self.passiveSymbol][-1].bidPrice1)/2
        midActive = (self.tickBufferDict[self.activeSymbol][-1].askPrice1 + self.tickBufferDict[self.activeSymbol][-1].bidPrice1)/2
        activeAsk1 = self.tickBufferDict[self.activeSymbol][-1].askPrice1
        activeBid1 = self.tickBufferDict[self.activeSymbol][-1].bidPrice1
        passiveAsk1 = self.tickBufferDict[self.passiveSymbol][-1].askPrice1
        passiveBid1 = self.tickBufferDict[self.passiveSymbol][-1].bidPrice1
        spread = midActive - midPassive 

        # 计算对手盘挂单数
        passiveBidVolume = int(np.mean(self.passiveBidVolume1[-30:])/2)
        passiveAskVolume = int(np.mean(self.passiveAskVolume1[-30:])/2)
        activeAskVolume = int(np.mean(self.activeAskVolume1[-30:])/2)
        activeBidVolume = int(np.mean(self.activeBidVolume1[-30:])/2)        

        ## 生成订单字典，通过字典管理订单
        # self.floorDict = {floor:{
        #                         'status_longActive':0,   # 止损时改为1 
        #                         'status_shortActive':0,   # 止损时改为1                            
        #                         'miu_longActive':self.miu,   # 记录均值
        #                         'miu_shortActive':self.miu,  # 记录均值
        #                         'floor_add':self.floor_add,  # 在短期价格和长期价格
        #                         'floor':floor,    # 对应的开仓阈值
        #                         'rever_floor':rever_floor,  # 对应的平仓阈值
        #                         'gap_base':self.gap_base,  # 对应的开始挂单阈值
        #                         'Time':datetime.now(),   # 之后用于存储开仓时间
        #                         'longActiveOpen':0,  # 主动多头被动空头的开仓挂单
        #                         'shortActiveOpen':0, # 主动空头被动多头的开仓挂单
        #                         'longAcivePos':0,    # 主动多头被动空头的持仓
        #                         'shortActivePos':0,  #主动空头被动多头的持仓  
        #                         'longActiveClose':0,  # 主动多头被动空头的平仓挂单
        #                         'shortActiveClose':0 # 主动空头被动多头的平仓挂单
        #                         'summean':0          # 基数
        #                         } for floor,rever_floor in zip(self.floors,self.rever_floors)}


        ### 首先撤掉所有的订单
        for orderID in list(self.cancelOrderDict):
            if self.cancelOrderDict[orderID] <= 1:
                self.cancelOrderDict[orderID] += 1
            else:
                self.cancelOrder(orderID)       
                self.cancelOrderDict[orderID] = 0

        ### 发开仓单，平仓单和止损逻辑       
        #  
        for level in self.floorDict:
            
            
            oneDict = self.floorDict[level]
            floor = oneDict['floor']*oneDict['summean'] + self.slipper*self.contractMinitick
            floor_add = oneDict['floor_add']*oneDict['summean']
            Time = oneDict['Time']  #该level最新的开仓sendOrderTime
            timeflow = min(0.0005*int((datetime.now()-Time).total_seconds()/600),0.003)
            rev_floor = (oneDict['rev_floor']-timeflow)*oneDict['summean']
            
            self.writeCtaLog('floor:%s内部仓位开始处理：sendOrderTime:%s, \
                            longActiveOpen:%s, longActivePos:%s, longActiveClose:%s, \
                            shortActiveOpen:%s, shortActivePos:%s, shortActiveClose:%s'%(
                                level, Time, 
                                oneDict['longActiveOpen'],oneDict['longActivePos'],oneDict['longActiveClose'],
                                oneDict['shortActiveOpen'],oneDict['shortActivePos'],oneDict['shortActiveClose']
                            ))            
            ### 处理主动空头被动多头平仓逻辑
            if oneDict['shortActivePos'] > 0 and oneDict['shortActiveClose'] == 0: #先处理主动空头被动多头平仓逻辑

                ### 先判断止损
                if ( datetime.now() - Time).total_seconds() > self.startSS and spread > oneDict['miu_shortActive'] + self.stopLoss*floor:
                    # 进入价格止损逻辑,平被动多头
                    orderid3 = self.sell(
                        self.passiveSymbol,
                        self.tickBufferDict[self.passiveSymbol][-1].lowerLimit+self.marketRatio*self.contractMinitick,
                        oneDict['shortActivePos']
                    )[0]
                    self.writeCtaLog('floor:%s 进入主动空头被动多头价格止损逻辑,止损订单:%s'%(level,orderid3))
                    self.floorDict[level]['shortActiveClose'] += oneDict['shortActivePos']
                    self.passiveSellMap[orderid3] = level
                    self.cancelOrderDict[orderid3] = 1  
                                                       
                elif ( datetime.now() - Time).total_seconds() > self.startTS:
                    # 进入时间止损逻辑,平被动多头
                    self.writeCtaLog('进入主动空头被动多头时间止损逻辑')
                    orderid3 = self.sell(
                        self.passiveSymbol,
                        self.tickBufferDict[self.passiveSymbol][-1].lowerLimit+self.marketRatio*self.contractMinitick,
                        oneDict['shortActivePos']
                    )[0]
                    self.writeCtaLog('floor:%s 进入主动空头被动多头时间止损逻辑,止损订单:%s'%(level,orderid3))
                    self.floorDict[level]['shortActiveClose'] += oneDict['shortActivePos']
                    self.passiveSellMap[orderid3] = level
                    self.cancelOrderDict[orderid3] = 1                      

                ### 在被动挂止盈单，sell
                elif ( datetime.now() - Time).total_seconds() > self.startTT:
                    volume =  self.tickBufferDict[self.activeSymbol][-1].askVolume1
                    orderid3 = self.sell(
                        self.passiveSymbol,
                        activeAsk1-oneDict['miu_shortActive']+rev_floor,
                        min(oneDict['shortActivePos'],volume)
                    )[0]
                    self.writeCtaLog('floor:%s 进入主动空头被动多头止盈逻辑,止盈订单:%s'%(level,orderid3))
                    self.passiveSellMap[orderid3] = level
                    self.cancelOrderDict[orderid3] = 1
                    self.floorDict[level]['shortActiveClose'] += min(oneDict['shortActivePos'],volume)
            
            ### 处理主动多头被动空头平仓逻辑
            if oneDict['longActivePos'] > 0 and oneDict['longActiveClose'] == 0:

                ### 先判断止损
                if ( datetime.now() - Time).total_seconds() > self.startSS and spread < oneDict['miu_longActive'] - self.stopLoss*floor:
                    orderid4 = self.cover(
                        self.passiveSymbol,
                        self.tickBufferDict[self.passiveSymbol][-1].upperLimit-self.marketRatio*self.contractMinitick,
                        oneDict['longActivePos']
                    )[0]
                    self.writeCtaLog('floor:%s 进入主动多头被动空头价格止损逻辑，止损订单:%s'%(level,orderid4))
                    self.floorDict[level]['longActiveClose'] += oneDict['longActivePos']
                    self.passiveCoverMap[orderid4] = level
                    self.cancelOrderDict[orderid4] = 1                   
                
                elif ( datetime.now() - Time).total_seconds() > self.startTS:
                    orderid4 = self.cover(
                        self.passiveSymbol,
                        self.tickBufferDict[self.passiveSymbol][-1].upperLimit-self.marketRatio*self.contractMinitick,
                        oneDict['longActivePos']
                    )[0]
                    self.writeCtaLog('floor:%s 进入主动多头被动空头时间止损逻辑,止损订单：%s'%(level,orderid4))
                    self.floorDict[level]['longActiveClose'] += oneDict['longActivePos']
                    self.passiveCoverMap[orderid4] = level
                    self.cancelOrderDict[orderid4] = 1                   

                ### 在被动挂止盈单，cover
                elif ( datetime.now() - Time).total_seconds() > self.startTT:
                    volume =  self.tickBufferDict[self.activeSymbol][-1].bidVolume1
                    orderid4 = self.cover(
                        self.passiveSymbol,
                        activeBid1-oneDict['miu_longActive']-rev_floor,
                        min(oneDict['longActivePos'],volume)
                    )[0]
                    self.writeCtaLog('floor:%s 进入主动多头被动空头止盈逻辑,止盈订单：%s'%(level,orderid4))
                    self.passiveCoverMap[orderid4] = level
                    self.cancelOrderDict[orderid4] = 1
                    self.floorDict[level]['longActiveClose'] += min(oneDict['longActivePos'],volume)
            
            ### 最近成交2s内不发新的开仓单，优先将资源分配给追单
            if (datetime.now()-self.lastMarketOrderTime).total_seconds()>2:
                ################## 处理主动空头被动多头开仓逻辑 #################
                if oneDict['shortActiveOpen']+oneDict['shortActivePos']<self.maxPos:
                    
                    # 进入正常发单逻辑, 检查是否修改thismiu
                    thismiu = self.miu if oneDict['shortActivePos']==0 else oneDict['miu_shortActive'] 
                                        
                    if spread > thismiu + self.spreadBand*self.summean and spread < thismiu + self.stopLossMarginCall*floor: # 主动开空被动开多
                        orderid1 = self.short(
                            self.activeSymbol,
                            passiveAsk1+max(thismiu+floor+floor_add,spread)+2*self.gap_base*(oneDict['shortActivePos']/self.maxPos),
                            min(self.posSize, self.maxPos - oneDict['shortActiveOpen']-oneDict['shortActivePos'],passiveAskVolume)
                        )[0]
                        self.activeShortMap[orderid1] = level
                        self.cancelOrderDict[orderid1] = 1
                        orderid2 = self.buy(
                            self.passiveSymbol,
                            activeBid1-max(thismiu+floor+floor_add,spread)-2*self.gap_base*(oneDict['shortActivePos']/self.maxPos),
                            min(self.posSize, self.maxPos - oneDict['shortActiveOpen']-oneDict['shortActivePos'],activeBidVolume)
                        )[0]
                        self.passiveBuyMap[orderid2] = level
                        self.cancelOrderDict[orderid2] = 1
                        self.writeCtaLog('floor:%s正常发出开仓单，主动开空:%s,被动开多:%s'%(level,orderid1,orderid2))
                        self.floorDict[level]['shortActiveOpen'] += min(self.posSize, self.maxPos - oneDict['shortActiveOpen']-oneDict['shortActivePos'],passiveAskVolume) \
                                                                    + min(self.posSize, self.maxPos - oneDict['shortActiveOpen']-oneDict['shortActivePos'],activeBidVolume)
                        self.floorDict[level]['miu_shortActive'] = thismiu
                
                ################### 处理主动多头被动空头开仓逻辑 #################################    
                
                if oneDict['longActiveOpen']+oneDict['longActivePos']<self.maxPos:
                    
                    ### 检查是否更新thismiu
                    thismiu = self.miu if oneDict['longActivePos'] == 0 else oneDict['miu_longActive']

                    if spread < thismiu - self.spreadBand*self.summean and spread> thismiu - self.stopLossMarginCall*floor: #主动开多被动开空
                        orderid1 = self.buy(
                            self.activeSymbol,
                            passiveBid1+min(thismiu-floor-floor_add,spread)-2*self.gap_base*(oneDict['longActivePos']/self.maxPos),
                            min(self.posSize,self.maxPos-oneDict['longActiveOpen']-oneDict['longActivePos'],passiveBidVolume)
                        )[0]
                        self.activeBuyMap[orderid1] = level
                        self.cancelOrderDict[orderid1] = 1

                        orderid2 = self.short(
                            self.passiveSymbol,
                            activeAsk1-min(thismiu-floor-floor_add,spread)+2*self.gap_base*(oneDict['longActivePos']/self.maxPos),
                            min(self.posSize,self.maxPos-oneDict['longActiveOpen']-oneDict['longActivePos'],activeAskVolume)
                        )[0]
                        self.passiveShortMap[orderid2] = level
                        self.cancelOrderDict[orderid2] = 1 
                        self.writeCtaLog('floor:%s正常发出开仓单，主动开多:%s，被动开空:%s'%(level,orderid1,orderid2))
                        self.floorDict[level]['longActiveOpen'] += min(self.posSize,self.maxPos-oneDict['longActiveOpen']-oneDict['longActivePos'],passiveBidVolume) \
                                                                + min(self.posSize,self.maxPos-oneDict['longActiveOpen']-oneDict['longActivePos'],activeAskVolume)
                        self.floorDict[level]['miu_longActive'] = thismiu
        
        # self.marketOrderDict[order1] = {
        #     'Time':datetime.now(),
        #     'type':'buy',
        #     'symbol':next_symbol,
        #     'volume':order.thisTradedVolume,
        #     'status':'wait'
        # } 
        ## 市价单未成交或拒单的追单逻辑
        for orderID in list(self.marketOrderDict):
            ### 这里写连续追单逻辑
            if self.marketOrderDict[orderID]['status']  == 'wait':
                if (datetime.now()-self.lastMarketOrderTime).total_seconds()>1:
                    self.cancelOrder(orderID)
                    self.writeCtaLog('订单%s未收到回报撤单重发'%orderID)
            elif self.marketOrderDict[orderID]['status'] == 'reject':
                self.writeCtaLog('订单%s被拒单重发'%orderID)
                orderMarket = self.marketOrderDict[orderID]
                orderid5 = self.followOrder(orderMarket['symbol'], orderMarket['type'], orderMarket['volume'])
                self.marketOrderDict[orderid5] = {
                    'Time':datetime.now(),
                    'type':orderMarket['type'],
                    'symbol':orderMarket['symbol'],
                    'volume':orderMarket['volume'],
                    'status':'wait',
                    'floor':self.marketOrderDict[orderID]['floor']                        
                }
                del self.marketOrderDict[orderID]


    # ----------------------------------------------------------------------
    def onBar(self, bar):
        """收到Bar推送（必须由用户继承实现）"""
        self.amDict[bar.vtSymbol].updateBar(bar)
        ## 无论是passiveSymbol先到还是activeSymbol先到，只记录正确的价差
        if bar.vtSymbol == self.passiveSymbol:
            self.passiveDatetime = datetime.now()
        else:
            self.activeDatetime = datetime.now()
        
        # 假定一分钟只有一根bar
        if abs((self.activeDatetime-self.passiveDatetime).total_seconds())<10:
            self.barSpreadBuffer.append(self.amDict[self.activeSymbol].close[-1]-self.amDict[self.passiveSymbol].close[-1])
            self.writeCtaLog('使用正确的两个bar计算价差')

            ########### 每分钟滚动计算miu ###############
            ## 只有当价差至少到达gap_base就可以开始发开仓单
            self.summean = np.mean(self.amDict[self.activeSymbol].close[-1] + self.amDict[self.passiveSymbol].close[-1])/2
            self.gap_base = 0.001*self.summean
            self.miu=np.mean(np.array(self.barSpreadBuffer[-self.forming:]))
            self.miu_long=np.mean(np.array(self.barSpreadBuffer[-self.forming*3:]))
               
            if abs(self.miu_long-self.miu)/self.summean > self.floors[0]:
                self.floor_add = abs(self.miu_long-self.miu)/self.summean
            else:
                self.floor_add = 0           
            self.writeCtaLog('参数更新成功, miu:%s, floor_add:%s'%(self.miu, self.floor_add))

        else:
            self.writeCtaLog('先来的bar抛弃')

        # delete too long data
        if len(self.tickBufferDict[self.activeSymbol])>=500 and len(self.tickBufferDict[self.passiveSymbol])>=500:
            del self.tickBufferDict[self.activeSymbol][:-100]
            del self.tickBufferDict[self.passiveSymbol][:-100]
        if len(self.barSpreadBuffer)==50:
            del self.barSpreadBuffer[:-10]
        
        ############## 按照时间修改posSize ###############
        Time = datetime.now()
        # 凌晨仓位减少
        if Time.hour < 8:
            self.posSize = self.posSize_night
            self.maxpos = self.maxPos_night
        else:
            self.posSize = self.posSize_day
            self.maxpos = self.maxPos_day
        
        pass


    # ----------------------------------------------------------------------
    def onTrade(self, trade):
        # 下单后报单
        # 根据成交的单修改limitOrderDict和CloseOrderLis写在了onOrder里
        pass

    # ----------------------------------------------------------------------
    def onStopOrder(self, so):
        """停止单推送"""
        pass
