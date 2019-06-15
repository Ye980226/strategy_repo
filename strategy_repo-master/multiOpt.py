import os,sys,time
import optimize as opt

strategy_list = ["btc_grid","btc_grid2"]
TEST_RUN = False
CACHE = False
start = time.time()

for strategy in strategy_list:
    if os.path.isdir(strategy):
        path = os.path.abspath(os.getcwd())
        os.chdir(strategy)
        sys.path.append(strategy)
        opt.runMemoryParallel(pardir = strategy, cache = CACHE, test_run = TEST_RUN)
        os.chdir(path)
print("---------- ALL STRATEGY DONE ----------")
print(f'TIME ELAPSE：{(time.time()-start)/3600} hour')