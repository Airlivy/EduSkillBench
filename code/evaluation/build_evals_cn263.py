"""Compile expanded cases; unreleased revisions require an isolated review-only output."""
from eval_compiler import main

if __name__=='__main__':
    main('data/single_turn_tasks_cn263.csv','skills/single_turn_cn263')
