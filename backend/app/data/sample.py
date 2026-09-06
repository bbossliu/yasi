from app.schemas import Annotation, BandScores, GradingResult

SAMPLE_PROMPT_TITLE = "科技话题：远程办公"
SAMPLE_PROMPT_TEXT = (
    "Some people believe that working from home benefits employees, "
    "while others think it brings more problems. "
    "Discuss both views and give your own opinion."
)

SAMPLE_ESSAY = """In recent years, more and more people choose to work from home. Some people think it is good for employees, but others believe it cause many problems. In my opinion, working from home has more advantages than disadvantages.

On the one hand, working from home can save a lot of time. People don't need to spend two hours on the bus or subway every day, so they can use this time to work or rest. Also, it is more comfortable. Employees can wear what they like and arrange their schedule freely. For example, a mother can take care of her children while she is working.

On the other hand, there are some problems. Firstly, people may feel lonely because they don't communicate with colleagues face to face. Secondly, it is hard to separate work and life. Many people find themself working at midnight, which is bad for their health. In addition, some managers think employees will be lazy without supervision.

In conclusion, although working from home has some disadvantages such as loneliness and blurred boundaries, I believe the benefits are greater. Companies should provide training to help employees adapt to this new way of working. This trend will probably continue in the future."""

SAMPLE_GRADING = GradingResult(
    bands=BandScores(task_response=6.5, coherence=6.5, lexical=5.5, grammar=5.5, overall=6.0),
    annotations=[
        Annotation(
            sentence_index=1,
            original="Some people think it is good for employees, but others believe it cause many problems.",
            issue="主谓一致错误：主语 it 为第三人称单数，动词应为 causes。",
            suggestion="Some people think it is good for employees, but others believe it causes many problems.",
            error_type="主谓一致",
        ),
        Annotation(
            sentence_index=4,
            original="People don't need to spend two hours on the bus or subway every day, so they can use this time to work or rest.",
            issue="词汇搭配：'on the bus or subway' 更地道的表达是 'commuting'；'this time' 指代略含糊。",
            suggestion="People no longer need to spend two hours commuting every day, so they can devote that time to work or rest.",
            error_type="词汇搭配",
        ),
        Annotation(
            sentence_index=10,
            original="Many people find themself working at midnight, which is bad for their health.",
            issue="单复数错误：themself 不是标准用法，主语为 many people，应为 themselves。",
            suggestion="Many people find themselves working at midnight, which is detrimental to their health.",
            error_type="单复数",
        ),
        Annotation(
            sentence_index=11,
            original="In addition, some managers think employees will be lazy without supervision.",
            issue="连接词单一：全文论证过渡仅依赖 Firstly/Secondly/In addition，缺乏更高阶的衔接手段。",
            suggestion="A further concern raised by some managers is that productivity may decline without direct supervision.",
            error_type="连接词",
        ),
    ],
    rewrite="""In recent years, an increasing number of employees have opted to work remotely. While some argue that this trend benefits workers, others contend that it gives rise to considerable difficulties. In my view, the advantages of working from home outweigh its drawbacks.

On the one hand, remote work eliminates the daily commute, allowing employees to reclaim hours that would otherwise be spent in transit. This time can be redirected towards productive work or much-needed rest. Moreover, the flexibility of home-based work enables individuals to structure their schedules around personal responsibilities. A parent, for instance, can attend to childcare while remaining professionally active.

On the other hand, working from home is not without its problems. The absence of face-to-face interaction may leave employees feeling isolated, which can erode team cohesion over time. Furthermore, the boundary between professional and private life tends to blur, with many people finding themselves working late into the night at the expense of their health. Some managers also worry that productivity may decline without direct supervision.

In conclusion, although remote working poses challenges such as social isolation and blurred work-life boundaries, I believe its benefits are more significant. Companies should invest in training and clear policies to help employees adapt to this new mode of work.""",
)
