#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# This file is part of archive2dna.
#
# archive2dna is free software: you can redistribute it and/or modify it under the terms of the GNU General Public License as published by the Free Software Foundation, either version 3 of the License, or (at your option) any later version.
# Foobar is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public License for more details.
# You should have received a copy of the GNU General Public License along with archive2dna. If not, see <https://www.gnu.org/licenses/>
#
# Author : Jan Krause-Bilvin
# First release: 2022-02-02 

################
### imports ####
################

# standard library
import math
import array
import io
import zipfile

# external
import numpy as np

# package
from . import dna
from . import bytesutils
from . import representation

#from reedsolo import RSCodec
from . import reedsolo
RSCodec = reedsolo.RSCodec

class Container:

    def __init__( self,
                      package_id = None,
                      primer_length = 5,    # in bytes, so 5*mi/2 -> 20 nucleotides
                      mi = 8,               # bits per inner symbol
                      mo = 14,              # pits per outer symbol
                      index_length    = 32, # in bits, so I  = 32 / (mi/2) = 8 symbols
                      index_positions = 24, # in bits, so I1 = 28 / (mi/2) = 7 symbols
                      N = 34,               # inner code lenght in symbols (message + error correctin symbols)
                      K = 30,               # inner code message in symbols
                      necso = None):

        # Primer : package identification in bytes
        self.primer_length = primer_length # 5 bytes -> 20 nucleotides
        
        # Index : numbering of segments
        self.index_length    = index_length    # total length in bits, nust be a multiple of mi
        self.index_positions = index_positions # length of segment id in bits, nust be a multiple of mi
        self.I   = index_length//mi              # length of the index in inner symbols
        self.dI  = index_length//2             # segment id in nucleotides
        self.I1  = index_positions//mi
        self.dI1 = index_positions//2 
        self.I2  = (index_length - index_positions)//mi
        self.dI2 = (index_length - index_positions)//2

        # Reed Solomon : coodword lengths in bits
        self.mi = mi        # inner code symbol size in bytes 
        self.mo = mo        # outer code
        self.dmi = mi//2    # inner code symbol size in DNA bases
        self.dmo = mo//2    # outer code

        # Reed Solomon inner code : redundancy inside fragments
        self.N  = N         # coded message length in symbols
        self.K  = K         # message length in symbols
        self.dK = K*mi//2   # in DNA bases
        self.dN = N*mi//2
        self.necsi = N-K    # error correcting sybols lenght
        self.dnecsi = self.necsi*self.mi//2 # necsi*dmi

        # Reed Solomon outer code : redundancy between fragments
        self.n  = 2**mo-1   # number of information symbols of outer code: 16383 nor mo=14
        self.dk = None      # dk = k*mo//2 , auto compute on basis of package file length
        self.dn = None      # dn is computed on basis of dk, i.e. dn = dk + dnecso
        self.necso = necso  # auto comupte based on package file length if none
        if necso is not None:
            self.dnecso = necso*self.mo//2

        # Mask : random bytes and integerts, generation: secrets.token_bytes(256) , random.randint(0,3S)
        self.rand_mask = b'\xaf\x92i\xa9\xf1\x0c"\xc2\xf4\xe4\xc6\xa80\'j\xc6w\x08h\xc8)H\xb9\xfa\xb5\x93&\x04!\xcd\xc7\xcbw\x98\x05Z\xda\x01\xacP\x05I\xbe\\y\x8e\xff\xb2\x13\\p\xab\xd8m\x19\x97\xae\xfe\xba\x04\x94\xc5\x90\xb1c\n\xa9[\\i\xfd\xc9^\xf8do\xc5\xa8\xceQ\x12\x01\xb9&n\xaa\xfa\xc9\xf8I\xe1\xc4\xc7g\x045#\x17\x9a`\x08s\x9fG\xd9Y\xbd\xb9R}=G|Ah\xd5\x93\xbd\xb3\nrJ\xf3~\xc6\xa6\xd0\xaeM\x1a:b\xf3*XR<\r\xe0-\xeb\xf5\xd8\x1c\xd7\xb6\x1f.\xe4\x04\x01rNoWkt\xad)\x9f\xd0\x8b\xf5\xe7\x021#\xc7\x85\xb3\xac(|D\xa1\x1c\x8f\x17\xc0<\xf4\xa3\x8d\xf0*\x92c\x00\x0b\xbf^\x88\x1a4\xdd\n\x97d>e[\n\xff\xe1\x01\xab\x98C\x07erG\xce\xdb\xa1m\x17\xab1D\x00\xda\xb3\x9c\xa0\x8b\x19P8\x16Cun\xd97`\xdf\xcd\x95\x9e\x0f9\x16\x90\xff\xfaJ\xe6\xb7\xbaI\x97\xda\xc2\xcd\x82'
        self.rand_ints  = [ 3, 2, 0, 3, 0, 0, 2, 3, 3, 3, 2, 3, 3, 3, 0, 3, 1, 1, 2, 1, 1, 1, 3, 2, 0, 1, 2, 1, 1, 1, 2, 0, 0, 0, 0, 2, 2, 0, 3, 0, 0, 2, 3, 3, 1, 2, 1, 0, 0, 2, 2, 0, 2, 2, 1, 0, 3, 1, 1, 3, 0, 3, 0, 3, 1, 1, 1, 2, 1, 0, 1, 2, 0, 3, 0, 1, 0, 0, 2, 1, 0, 0, 2, 0, 1, 0, 1, 0, 0, 0, 0, 2, 3, 1, 1, 0, 0, 2, 2, 3, 1, 1, 3, 2, 1, 1, 1, 2, 0, 3, 1, 0, 2, 0, 1, 0, 0, 3, 2, 1, 1, 0, 3, 0, 2, 1, 0, 3, 2, 1, 1, 0, 3, 2, 0, 3, 3, 2, 0, 0, 0, 0, 3, 1, 2, 2, 3, 2, 3, 0, 0, 2, 2, 1, 3, 2, 2, 3, 3, 3, 1, 3, 2, 0, 3, 1, 2, 2, 2, 0, 3, 3, 3, 3, 0, 3, 3, 1, 0, 2, 0, 1, 2, 0, 0, 3, 2, 3, 1, 0, 0, 1, 2, 3, 1, 0, 3, 0, 1, 1, 0, 0, 2, 2, 3, 2, 1, 3, 2, 3, 1, 1, 3, 3, 1, 1, 3, 2, 2, 3, 0, 0, 0, 2, 0, 3, 2, 3, 1, 1, 3, 2, 2, 0, 0, 1, 1, 1, 3, 3, 3, 0, 2, 2, 2, 2, 3, 1, 1, 2, 0, 3, 0, 0, 3, 2]

        # Package id and primer
        self.primer_length = primer_length
        if package_id == None:
            self.package_id = None
            self.primer = None
        else:
            self.package_id = package_id
            self.primer = dna.id2primer( package_id, length=primer_length)
            
        # Data : 2D array, each element corresponds to a DNA base 
        # The actual quantity of information of an element is 2 bits
        # but it is stored on a byte.
        self.data = None
        
        # DNA segments
        self.dna = None
        self.segmants_count = None
        self.segments_sizes = None
        self.segments_median_size = None
        self.segments_max_size = None
        self.segments_min_size = None
        self.segments_average_size = None
        self.segments_max_size = None

        # Statistics
        self.inner_redundancy = None
        self.outer_redundancy = None

        self.inner_corrections = 0
        self.outer_corrections = 0
        self.segments_beyond_repair = 0
        self.segments_lost = 0        
        self.binary_size = None
        self.error = False
        self.error_message = ''
        
        # Debug_output
        self.debug_output = False
        
    ###################
    ### Random mask ###
    ###################

    def xor_bytes(self, x1_bytes, x2_bytes):
        """Bitwise XOR on bytes strings"""
        return bytes([_x1 ^ _x2 for _x1, _x2 in zip(x1_bytes, x2_bytes)])

    def mask_bytes(self, binary_data):
        """Masks byte using a XOR"""
        dlen = len(binary_data)
        rlen = len(self.rand_mask)
        nchunks = dlen//rlen
        nrest = dlen%rlen
        dataRA = b''
        j = 0
        for i in range(nchunks):
            j = i
            dataRA +=  self.xor_bytes( binary_data[i*rlen : (i+1)*rlen] , self.rand_mask ) 
        dataRA += self.xor_bytes( binary_data[(j+1)*rlen : (j+1)*rlen + nrest] , self.rand_mask[:nrest] ) 
        return dataRA


    ###########################
    ### Data input : binary ###
    ###########################
    
    def load_binary(self, binary_data):
        """Reads a binary file, applies random mask, reshapes to table.
           Binary data is stored by columns: first column 1 is filled,
           then column 2, and so on."""
        self.binary_size = len(binary_data)
        # zip data
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "a", zipfile.ZIP_DEFLATED, False) as zip_file:
             zip_file.writestr('information_package', io.BytesIO( binary_data ).getvalue() )
        binary_data = zip_buffer.getvalue()
        del( zip_buffer )
        # mask data
        binary_data = self.mask_bytes(binary_data)
        binary_data = bytesutils.split_bytes_in_four(binary_data)

        # representation way
        self.dk = len(binary_data) // (self.dK-self.dI)
        if len(binary_data) % (self.dK-self.dI) != 0: # if last segment is not full
            self.dk += 1  

        # If outer code lenght self.necso is not specified, 
        # auto compute so we have about 40% outer redundancy
        pr = 0.4 # goal: 40% redundancy
        if self.necso == None:
            dmo = self.mo // 2
            dnecso = int( pr / (1 - pr) * self.dk)
            dnecso_e = dnecso // dmo + 1
            dnecso = dnecso_e * dmo
            self.dnecso = dnecso
            self.necso  = dnecso // dmo

        # set total number of columns
        self.dn = self.dk + self.dnecso
                
        # load data    
        n_lines   = self.dK-self.dI
        n_columns = self.dk
        self.data = representation.Representation( data_bytes=binary_data,
                                                   n_lines = n_lines,
                                                   n_columns = n_columns )

        # shift extend data to final structure dn x dk                                           
        delta_lines   = self.dN - n_lines
        self.data.insertlines(0,n=delta_lines)        

        self.data.insertcolumns(0,n=self.dnecso)

     
    ##################################
    ### Create logical redundancy  ###
    ##################################
        
    def add_outer_code(self):
        """Computes outer code error correcing symbols and initializes data with encoded messages 
           (=  error correcting codes + message). The outer code is applied between segments
           i.e. over each line of the data array.
           """

        # Initialize Reed Solomon outer coder
        outerCoder =  RSCodec(self.necso, nsize=self.n) # Using n-k = necs error correcting codes
        
        ## numpy way
        n_lines   = self.dK-self.dI
        n_columns = self.dk
        line_offset_ori   = self.dN - n_lines

        
        data = self.data.tonumpy()
        
        # Create error outer correcting code sybolsline by bline    
        for i in range(self.dK-self.dI):
        
            # Read line in DNA representation
            dline = self.data.getline( i+line_offset_ori )[self.dnecso:]
            line_array = array.array('i', list(dline))
            line_array_mo = dna.merge_bases(line_array, block_size=self.dmo)
            
            # Run Reed Solomon to compute error correctig symblos
            line2 = outerCoder.encode( line_array_mo )
            ecc = line2[-self.necso:]
            ecc_bases = dna.split_bases( ecc, block_size=self.dmo )
            
            # Store coded_message (= message + ecc) in data
            line_offset = self.dnecsi + self.dI            
            out = list(ecc_bases) +  list(line_array)
            for b in range(len(out)):
                self.data.setpos( i+line_offset , b , out[b]) 


    def add_index(self):
        """Adds index i.e. the identification of DNA segments (1 segment = 1 column):
        1) Secion I1: number segments starting at 1. Note: 0 is reserved for lost/destroyed segments.
        2) Sction I2: adds partial countdowns to end of error corecting symbols and end of block.
           countdowns ent at 1, i.e. 1 is the last ecc and the last symbol of block.
           Goal: auto detect parameters when reading back DNA, namely dn and dnecso.
        """
        # TODO: hardocoded for mi=8, to be generalized
        
       # Numerus currens of segments, starts at 0 (in index block I1)
        for i in range(self.data.size[1]):
        #for i in self.data.column_indexes():
            b = dna.int2bytes(i, n=self.index_positions//8)
            for j in range(self.index_positions//8):
                x = b[j].to_bytes(1,'big')
                x4 = bytesutils.split_bytes_in_four(x)
                for l in range(len(x4)):
                    self.data.setpos( self.dnecsi + 4*j+l, i , x4[l] )
            
        # Count down for end of segment, ends at 0 (iin index block I2)
        max_range = min([ self.data.size[1], 2**(self.index_length - self.index_positions)-1])
        for i in range(max_range):
            b = dna.int2bytes(i, n=1)
            x4 = bytesutils.split_bytes_in_four(b)
            for l in range(len(x4)):
                self.data.setpos( self.dnecsi + l+self.dI1, self.data.size[1]-i-1 , x4[l] )

        # Count down for end of outer code ecc, ends at 0 (in index block I2)
        for i in range(max_range):
            b = dna.int2bytes(i, n=1)
            x4 = bytesutils.split_bytes_in_four(b)
            for l in range(len(x4)):
                self.data.setpos( self.dnecsi + l+self.dI1, self.dnecso-i-1 , x4[l] ) 

        # Mask index using random numbers
        for i in range(self.data.size[1]):
            for j in range(self.dI): #index_length//8
                value = self.data.getpos( self.dnecsi + j, i)
                masked_value = ( value ^ self.rand_ints[j%len(self.rand_ints)] ) % 4
                self.data.setpos( self.dnecsi + j, i , masked_value ) #4*j+l

    def add_inner_code(self):
        """ Adds inner code, i.e. the correcting code of each DNA segment. 
            Segments correspond to data columns."""
        # Initialize inner coder
        innerCoder =  RSCodec(self.necsi, c_exp=self.mi)
        
        for i in range(self.dn):
            dcol = self.data.getcolumn( i )[self.dnecsi:]
            darray = array.array('i', list(dcol))
            
            # merging bases    
            darray_mi = dna.merge_bases(darray, block_size=self.dmi)           
            darray_mi_ba = bytearray( list(darray_mi) )
            
            # encode from bytes, which are enough for mi<=8
            # wiil return type bytearray even if input is array anyway !
            msg_coded = innerCoder.encode( bytes(darray_mi_ba) ) 
            
            # store error correcting code symbols
            ecc  = msg_coded[-self.necsi:]
            ecc_bases = dna.split_bases(ecc, block_size=self.dmi)
            for j in range(len(ecc_bases)):
                self.data.setpos(j , i, ecc_bases[j])                    

    def create_logical_redundancy(self):
        """Adds outer code, index, innercode"""
        self.add_outer_code()
        self.add_index()
        self.add_inner_code()
        
    ######################
    ### Convert to DNA ###
    ######################

    def to_dna(self):
        """Converts data into DNA segments"""
        self.dna = []
        for i in sorted(self.data.column_indexes()):
           col = self.data.getcolumn(i)
           DNA_segment = ''
           for j in range(len(col)):
                DNA_segment += dna.bits2dna( col[j] )
           self.dna.append(DNA_segment)

    def add_primers(self):
        """Adds primer and its complements around each DNA segment."""       
        if self.primer is not None:
            comp_primer = dna.complement_primer(self.primer)
            self.dna = [ dna.add_primers( x, 
                              primer1=self.primer,
                              primer2=comp_primer ) for x in self.dna ]
                              
    def remove_primers(self):
        """Removes primer and its complements around each DNA segment."""  
        if self.primer is not None:
            comp_primer = dna.complement_primer(self.primer)
            self.dna = [ dna.remove_primers( x, 
                                  primer1=self.primer,
                                  primer2=comp_primer ) for x in self.dna ]
                                          
    def convert_to_dna(self):
        """Converts data to DNA segments and adds primers around each segment."""
        self.to_dna()
        self.add_primers()
                                  
    #########################
    ### Data output : DNA ###
    #########################
                                  
    def write_dna(self):
        """Returns a DNA string, with one line per DNA segment (e.g. to be written in a text file)."""
        return '\n'.join(self.dna)

    ########################
    ### Data input : DNA ###
    ########################

    def read_dna(self, text):
        """Reads DNA strings from a text file: one line per DNA segment"""
        self.dna = text.split('\n')
        self.dna = [ dna.stripDna(s) for s in self.dna ]
        if '' in self.dna:
            self.dna.remove('')

    def compute_segments_sizes(self):
        """Compute DNA segments sizes, as well as max, median and average length"""
        ss = np.full( (len(self.dna),), 0 )        
        for i in range(len(self.dna)):
            ss[i] =  len(self.dna[i]) 
        self.segments_sizes = ss
        self.segments_max_size = ss.max()
        self.segments_min_size = ss.min()
        self.segments_average_size = ss.mean()
        self.segments_median_size = int(np.median(ss))
    
    def dna_to_array(self):
        """Reformats DNA segments strings into array"""
        
        self.data = representation.Representation( data_dna=self.dna,
                                                   n_lines = self.segments_max_size,
                                                   n_columns = len(self.dna) )   
    
                
    def load_dna(self, text):
        """Reads DNA text, remove primers around each segment, compute segments size-statistics, converts to 2D data array."""
        self.read_dna(text)
        self.remove_primers()
        self.compute_segments_sizes()
        self.dna_to_array()

    #############################################
    ### Check and correct logical redundancy  ###
    #############################################
                
    def decode_inner_code(self):
        """Decode inner code"""
        
        innerCoder =  RSCodec(self.necsi, c_exp=self.mi)

        segments_to_destroy = []

        for i in range(self.data.size[1]):
            #print('---- inner code - decoding segment', i , '----')

            # Read inner code : message       
            #dcol = dna.get_bytearray( self.data[self.dnecsi:,i] )
            dcol = self.data.getcolumn( i )[self.dnecsi:]
            darray = array.array('i', list(dcol))
            darray_mi = dna.merge_bases(darray, block_size=self.dmi)
            
            # Read inner code : ecc      
            #ecc = dna.get_bytearray( self.data[:self.dnecsi,i] )
            ecc = self.data.getcolumn( i )[:self.dnecsi]
            ecc2 = array.array('i', list(ecc))
            ecc_mi = dna.merge_bases(ecc2, block_size=self.dmi) 
            
            # Compute coded message to decode
            darray_ba = bytearray(list(darray_mi))
            ecc_ba = bytearray(list(ecc_mi))
            coded_msg_ba = darray_ba + ecc_ba

            n_corrections = 0
            try: 
                decoded_msg, decoded_msgecc, errata_pos = innerCoder.decode( bytes(coded_msg_ba) )
                n_corrections = len(errata_pos)

            except Exception as e:
                self.segments_beyond_repair += 1
                segments_to_destroy.append(i)   
             
            if n_corrections > 0:
                # we need to convert decoded message to bases to do corrections
                decoded_bases = dna.split_bases(decoded_msg, block_size=self.dmi)
                decoded_ecc   = dna.split_bases(decoded_msgecc, block_size=self.dmi)[-self.dnecsi:]
                scope = min( [ len(decoded_bases), len( self.data[self.dnecsi:,i] ) ] ) 
                for j in range( scope ):
                    if self.data[self.dnecsi+j,i] != decoded_bases[j] :
                        self.inner_corrections += 1
                        self.data.setpos( self.dnecsi+j, i , decoded_bases[j] )

        #self.data = np.delete( self.data, [segments_to_destroy], axis=1 )
        for i in reversed( sorted(segments_to_destroy)):
           self.data.pop(i)
           self.data.size[2] -= 1
                                  

    def sort_segments(self):
        """Sorts segments by their index. If a segment is not there its columns is empty: it 
        will be used later to restore the segment using the Reed Solomon outer code.
        In order to determine the number of the last segment even if it was lost the
        countdown in I2 is used. The same principle is applied for necso."""
    
        #indices = np.full((self.data.shape[1],), None, dtype=object)
        #count_down = np.full((self.data.shape[1],), None, dtype=object)
        

        # Get positions for all segments

        def get_index(a):
            """Computes integer value of DNA segment"""
            bytes_index = bytearray()
            for i in range(len(a)):
                bytes_index.append( a[i] )
            bytes_index2 = bytesutils.merge_four_bytes_in_one(bytes_index)
            idx = int.from_bytes(bytes_index2, byteorder='big')
            return(idx)

        indices = []
        count_down = []
        for i in range(self.data.size[1]):
          
            #index_col = self.data.getcolumn(i)[self.dnecsi:self.dnecsi+self.dI] 
            masked_index = self.data.getcolumn(i)[self.dnecsi:self.dnecsi+self.dI]
            index_col = []
            for j in range(len(masked_index)):
                index_col.append( ( masked_index[j] ^ self.rand_ints[j%len(self.rand_ints)] ) % 4 )          

            indices.append( get_index( index_col[:self.dI1] ) )
            count_down.append( get_index( index_col[self.dI1:] ) )
            
            self.data.data[i]['index'] = indices[i]
            
        # Compute last segment position even if it was lost (using second countdown in I2)
            
        last_index = None
        for i in range(len(count_down)):
            if count_down[-i] != 0: # take fisrt index for non null countdowns
                last_index = indices[-i] + count_down[-i]
                break

        # Find missing segments indices (if any)
        def missing_indices(l):
            l2 = sorted(l)
            start, end = l2[0], l2[-1]
            return sorted(set(range(start, end + 1)).difference(l2))            
        missing_indx = missing_indices(indices)
        self.segments_lost += len(missing_indx)

        # Extend data array with missing or unrecovered DNA segments (if required)
        if last_index > max(indices):
            missing_indx2 = range( max(indices)+1, last_index+1 )
            missing_indx = missing_indx + missing_indx2
        for x in missing_indx:
            self.data.insertcolumns(x)
        
        # Sort data array according to index
        self.data.reindex_columns()
                
        # Auto determine necso (using first countdown in I2)
        if self.necso is None:
            for i in range(len(count_down)):
                if count_down[i] != 0:
                    self.dnecso = indices[i] + count_down[i] + 1
                    self.necso = self.dnecso // self.dmo
                    break


    def decode_outer_code(self):
        """Decodes Reed Solomon outer code: restore and correct segments"""
        outerCoder =  RSCodec(self.necso, nsize=self.n) 
        line_offset = self.dnecsi + self.dI
        for i in range(self.data.size[0]-line_offset):
            
            dline = self.data.getline( i+line_offset )
            ecc = dline[:(self.necso*self.dmo)]
            msg = dline[(self.necso*self.dmo):]

            msga = array.array('i', list(msg))  
            ecca = array.array('i', list(ecc))  
                
            msgm = dna.merge_bases(msga, block_size=self.dmo) 
            eccm = dna.merge_bases(ecca, block_size=self.dmo)

            try:
                n_corrections = 0
                decoded_block, decoded_msgecc, errata_pos = outerCoder.decode(msgm+eccm)
                n_corrections = len(errata_pos)
            except Exception as e:

                self.error = True
                self.error_message += 'Decode outer code error on line ' +\
                                       str(i) +\
                                       '. Error: ' +\
                                       str(e)
                                    
            if n_corrections > 0:
                self.outer_corrections += n_corrections
                decoded_bases = dna.split_bases(decoded_block, block_size=self.dmo)
                db = list(decoded_bases)
                scope = min( [ len(decoded_bases), len( self.data[i+line_offset,self.dnecso:] ) ] ) 
                for j in range( scope ) :
                    self.data.setpos( i+line_offset,self.dnecso+j , db[j] )
 
                
    def check_and_correct_logical_redundancy(self):
        """Processes logical redundency: decode innercode, sort segments and decodes outer code."""
        self.decode_inner_code()
        self.sort_segments()
        self.decode_outer_code()
                
    ############################
    ### Data output : binary ###
    ############################
        
    def write_binary(self):
        """Writes 2D DNA data array to binary data."""

        line_offset = self.dnecsi+self.dI
                
        self.binary_data = b''
        for i in sorted( self.data.column_indexes() ):
            if i >= (self.necso*self.dmo):
                col = self.data.getcolumn(i)[line_offset:]
                for b in col:
                    self.binary_data += dna.int2bytes(b, n=1)
                
        self.binary_data = bytesutils.merge_four_bytes_in_one(self.binary_data)
              
        self.binary_data = self.mask_bytes(self.binary_data)
        
        zip_buffer2 = io.BytesIO( self.binary_data )
        with zipfile.ZipFile(zip_buffer2, "a", zipfile.ZIP_DEFLATED, False) as zip_file:
            self.binary_data = zip_file.read('information_package')
        del( zip_buffer2 )
       
        self.binary_size = len(self.binary_data)
        return self.binary_data 

    ##################
    ### Statistics ###
    ##################
    
    def compute_stats(self):
        """Compute statistics"""
        # segments
        self.segments_count = len(self.dna)
        # redundancy
        self.inner_redundancy = (self.N-self.K)/self.N
        self.outer_redundancy = self.dnecso/self.segments_count

        return {'redundancy'   : { 'inner': str(self.inner_redundancy),
                                   'outer': str(self.outer_redundancy) },
                'dna_segments' : { 'size_median': str(self.segments_median_size),
                                   'size_min': str(self.segments_min_size),
                                   'count': str(self.segments_count) },
                'binary_data'  : { 'size_bytes': str(self.binary_size),
                                   'blocks': str(1) },
                'capacity'     : { 'max_segments_block': str(self.n),
                                   'block_capacity_bytes': str( self.n * ((self.K-self.I)*self.mi//8)  ),
                                   'max_segments_index': str( 2**(self.I1*self.mi)-1 ),
                                   'total_capacity_bytes': str( (2**(self.I1*self.mi)-1) * ((self.K-self.I)*self.mi//8)  )},
                'parameters'   : { 'mo': str(self.mo),
                                   'mi': str(self.mi),
                                   'N': str(self.N),
                                   'K': str(self.K),
                                   'necsi': str(self.necsi),
                                   'n_max': str(self.n),
                                   'k_max': str(self.n - self.necso),
                                   'necso': str(self.necso),
                                   'I': str(self.I),
                                   'I1': str(self.I1),
                                   'I2': str(self.I2) },
                'corrections'  : { 'inner': str(self.inner_corrections),
                                   'outer': str(self.outer_corrections),
                                   'segments_beyond_repair': str(self.segments_beyond_repair),
                                   'segments_lost': str(self.segments_lost)},
                'errors'       : { 'error': str(self.error) ,
                                   'message': str(self.error_message)},
                'id'           : { 'package_id': str(self.package_id),
                                   'package_primer' : str(self.primer) } }   
        
        
                
         
