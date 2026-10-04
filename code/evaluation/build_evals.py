"""Compile the original task schema while retaining rubric weights; paths are explicit options."""
from eval_compiler import main

if __name__=='__main__':
    main('data/single_turn_tasks.csv','skills/single_turn')
