import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F

from modules.activations import swish
from modules.bessel_basis_layer import BesselBasisLayer
from modules.spherical_basis_layer import SphericalBasisLayer
from modules.embedding_block import EmbeddingBlock
from modules.output_block import OutputBlock
from modules.interaction_block import InteractionBlock

class DimeNet(nn.Module):
    """
    DimeNet model.

    Parameters
    ----------
    emb_size
        Embedding size used throughout the model
    num_blocks
        Number of building blocks to be stacked
    num_bilinear
        Third dimension of the bilinear layer tensor
    num_spherical
        Number of spherical harmonics
    num_radial
        Number of radial basis functions
    envelope_exponent
        Shape of the smooth cutoff
    cutoff
        Cutoff distance for interatomic interactions
    num_before_skip
        Number of residual layers in interaction block before skip connection
    num_after_skip
        Number of residual layers in interaction block after skip connection
    num_dense_output
        Number of dense layers for the output blocks
    num_targets
        Number of targets to predict
    activation
        Activation function
    """
    def __init__(self,
                 emb_size,
                 num_blocks,
                 num_bilinear,
                 num_spherical,
                 num_radial,
                 cutoff=5.0,
                 envelope_exponent=5,
                 num_before_skip=1,
                 num_after_skip=2,
                 num_dense_output=3,
                 num_targets=12,
                 activation=swish):
        super(DimeNet, self).__init__()

        self.num_blocks = num_blocks

        # cosine basis function expansion layer
        self.rbf_layer = BesselBasisLayer(num_radial=num_radial,
                                          cutoff=cutoff,
                                          envelope_exponent=envelope_exponent)

        self.sbf_layer = SphericalBasisLayer(num_spherical=num_spherical,
                                             num_radial=num_radial,
                                             cutoff=cutoff,
                                             envelope_exponent=envelope_exponent)
        
        # embedding block
        self.emb_block = EmbeddingBlock(emb_size=emb_size,
                                        num_radial=num_radial,
                                        activation=activation)
        
        # output block
        self.output_blocks = nn.ModuleList({
            OutputBlock(emb_size=emb_size,
                        num_radial=num_radial,
                        num_dense=num_dense_output,
                        num_targets=num_targets,
                        activation=activation) for _ in range(num_blocks + 1)
        })

        # interaction block
        self.interaction_blocks = nn.ModuleList({
            InteractionBlock(emb_size=emb_size,
                             num_radial=num_radial,
                             num_spherical=num_spherical,
                             cutoff=cutoff,
                             envelope_exponent=envelope_exponent,
                             num_bilinear=num_bilinear,
                             num_before_skip=num_before_skip,
                             num_after_skip=num_after_skip,
                             sph_funcs=self.sbf_layer.get_sph_funcs(),
                             activation=activation) for _ in range(num_blocks)
        })
    
    def forward(self, g):
        # add rbf features for each edge in one batch graph, [num_radial,]
        g = self.rbf_layer(g)
        # Embedding block
        g = self.emb_block(g)
        # Output block
        P = self.output_blocks[0](g)  # [batch_size, num_targets]
        # Interaction blocks
        for i in range(self.num_blocks):
            g = self.interaction_blocks[i](g)
            P += self.output_blocks[i + 1](g)
        
        return P