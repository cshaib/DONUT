import os
import time

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

import torch
import torch.nn as nn
from torch.utils.data import TensorDataset, DataLoader

from tqdm import tqdm
from sklearn.preprocessing import MinMaxScaler

from ctcdecode import CTCBeamDecoder
from model import LabelModel

from blick import BlickLoader

def train_label_model(label_train_loader, num_labels, learn_rate, hidden_dim=256, EPOCHS=5):
    
    ####################### TODO: Add to config file ####################### 

    # Setting common hyperparameters
    input_dim = next(iter(label_train_loader))[0].shape[2]
    output_dim = num_labels + 1 # len labels that I want to output (length of the num diff labels + CTC blank symbol)
    n_layers = 3 # following paper params

    # create model
    label_model = LabelModel(input_dim=input_dim, hidden_dim=96, output_dim=output_dim, n_layers=3)

    label_model.to(device)
    
    # Defining loss function and optimizer
    criterion = nn.CTCLoss(reduction=None)
    optimizer = torch.optim.Adam(label_model.parameters(), lr=learn_rate)
    
    label_model.train()

    print("Pre-training label model.")

    epoch_times = []

    for epoch in range(1,EPOCHS+1):
        start_time = time.clock()
        h = label_model.init_hidden(batch_size)

        avg_loss = 0.
        counter = 0
        
        for counter, x, label in enumerate(label_train_loader):
        
            h = h.data

            label_model.zero_grad()
            
            out, h = label_model(x.to(device).float(), h)

            loss = criterion(out, label.to(device).float())
            loss.backward()
            optimizer.step()
            avg_loss += loss.item()

            if counter%200 == 0:
                print(f"Epoch {epoch}......Step: {counter}/{len(label_train_loader)}....... \
                        Average Loss for Epoch: {avg_loss/counter}")
        
        current_time = time.clock()
        print(f"Epoch {epoch}/{EPOCHS} Done, Total Loss: {avg_loss/len(label_train_loader)}")

        print(f"Total Time Elapsed: {str(current_time-start_time)} seconds")

        epoch_times.append(current_time-start_time)

    print("Total Training Time: {} seconds".format(str(sum(epoch_times))))

    torch.save(label_model, "pretrained_label_model.pt")

    return label_model


def train_wakeword_model(audio_train_loader, vocab_list, label_model, beam_size=3, num_hypotheses=5, query_by_string=False):
    wakeword_model = {}

    if query_by_string: 
        # load ww model produced by MFA from config 
        keywords = config["wakeword_model"]
        # load blick 
        b = BlickLoader

        for i, _, y_hat in enumerate(keywords.items()): 
            w = b.assessWord(y_hat)
            # for each keyword, append the tuple(hypotheses + weights) to the list 
            # only one hypothesis if using MFA 
            wakeword_model[i] = (y_hat, w)

    else:
        # train ww model from scratch   
        for i in audio_train_loader:
            posteriors_i = label_model(i)
            # decode using CTC, vocab_list is A (labels)
            decoder = CTCBeamDecoder(self.vocab_list, beam_width=self.beam_size,
                                    blank_id=self.vocab_list.index('_'))

            beam, beam_scores, _, _ = decoder.decode(posteriors_i)

            for j in range(num_hypotheses):
                y_hat = beam[j] # hypothesis
                log_prob_post = beam_scores[j]
                w = log_prob_post ** -1

                # for each keyword, append the tuple(hypotheses + weights) to the list
                wakeword_model[i].append((y_hat, w))

    return wakeword_model


def evaluate_audio(audio, wakeword_model, label_model):
    label_model.eval()
    CTCForward = nn.CTCLoss(reduction=None)

    posterior_test = label_model(audio)
    score = 0

    for y_hat, w in wakeword_model.values():
        log_prob_post_test = CTCForward(posterior_test, y_hat)

        score += score + log_prob_post_test * w

    return score
