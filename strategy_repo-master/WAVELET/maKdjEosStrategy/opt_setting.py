# encoding= utf-8

# 指定要优化的策略
import numpy as np
STRATEGYCLASS = {'maKdjStrategyV3': 'maKdjStrategy'}

# 指定引擎设置
ENGINESETTING = {
                "startDate": "20180701 00:00:00",
                "endDate": "20190222 23:59:00",
                "slippage": 0.002,
                "rate": 0.5,
                # 'setDB_URI': "mongodb://192.168.0.104:27017",
                "dbName": "VnTrader_1Min_Db",
                "symbolList":["eos.usd.q:okef"]
                }

# 优化目标
OPT_TARGET = "sharpeRatio"
# np.arange(0.1,0.2,0.01)
# range(1,10,1)
# 指定优化任务
OPT_TASK = [        
            {"pick_best_param": 
                {
                "maPeriod": range(220,360,10),
                "maType": [0,1,6],
                }
            },
            {"pick_best_param": 
                {
                "fastkPeriod": range(2,10,1),
                "slowkPeriod": range(2,10,1),
                "slowdPeriod": range(14,32,2)
                }
            },
            {"pick_best_param": 
                {
                "lowKdjThreshold": range(20,41,4),
                "highKdjThreshold": range(60,81,4),
                }
            },
            {"pick_best_param": 
                {
                "takeProfitPct": np.arange(0.03, 0.081,0.005),
                "stopLossPct":  np.arange(0.02, 0.04,0.005)
                }
            }
]

