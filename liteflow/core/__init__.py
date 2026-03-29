class Workflow:
    pass


class StepBody:
    pass


class WorkflowBuilder:
    pass


class ExecutionResult:
    pass


class StepExecutionContext:
    pass


def Flow(name):
    def decorator(cls):
        cls.__flow_name__ = name
        cls.__steps__ = {}
        
        # 收集所有带 @step 装饰器的方法
        for attr_name in dir(cls):
            if not attr_name.startswith('__'):
                attr = getattr(cls, attr_name)
                if hasattr(attr, '__step_name__'):
                    step_name = attr.__step_name__
                    deps = getattr(attr, '__step_deps__', [])
                    cls.__steps__[step_name] = {
                        'method': attr,
                        'deps': deps
                    }
        
        # 添加 execute 方法
        def execute(self, data):
            context = {}
            
            # 拓扑排序处理依赖
            def topological_sort(steps):
                visited = set()
                temp = set()
                order = []
                
                def visit(step_name):
                    if step_name in temp:
                        raise ValueError(f"循环依赖: {step_name}")
                    if step_name not in visited:
                        temp.add(step_name)
                        for dep in steps[step_name]['deps']:
                            if dep in steps:
                                visit(dep)
                        temp.remove(step_name)
                        visited.add(step_name)
                        order.append(step_name)
                
                for step_name in steps:
                    if step_name not in visited:
                        visit(step_name)
                return order
            
            # 执行步骤
            step_order = topological_sort(self.__steps__)
            for step_name in step_order:
                step_info = self.__steps__[step_name]
                method = step_info['method']
                
                # 准备参数
                if step_name == 'parse_req':  # 第一个步骤
                    result = method(self, data)
                else:
                    result = method(self, context)
                
                # 存储结果
                context[step_name] = result
            
            return context
        
        cls.execute = execute
        return cls
    return decorator


def step(name, deps=None):
    if deps is None:
        deps = []
    
    def decorator(func):
        func.__step_name__ = name
        func.__step_deps__ = deps
        return func
    return decorator